package stage4.rng;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.IdentityHashMap;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.apache.cassandra.db.ReadCommand;
import org.apache.cassandra.db.ReadResponse;
import org.apache.cassandra.net.Message;

/**
 * Stage-4 harness, cluster tier (amendment C5 of 2026-10-27) of max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
 * Observe-only helper called from rng.btm on node 1 (on the system class path via the agent's sys: option). For range reads of rng.t:
 *   BEGIN,<q>,<epoch ms>,gc=<0|1>                                       RangeCommandIterator constructed (gc mode if the flag file exists)
 *   BATCH,<q>,<b>,cf=,max=,rq0=,live=,total=,req=,vn=,rq1=,br=          one per sendNextRequests: fields at entry, query() calls and vnodes, fields at exit
 *   RESP,<q>,<ms since begin>,<from>,<array length>,<remaining>,<closed 0|1>,<class>   one per ReadCallback.onResponse
 *   CLOSE,<q>,<ms>,cap=,nb=,H=,gc=,live0=,live1=,nend=,Hend=            RangeCommandIterator.close(): responses/bytes delivered before close
 * In gc mode, live0 is taken at the first sendNextRequests and live1 at close, each the "Total" bytes of an in-process GC.class_histogram
 * (DiagnosticCommand gcClassHistogram: a full GC, live objects only). Nothing is changed in the node's behaviour except the time those take.
 * Output file: -Drng.out; flag file: -Drng.flag.
 */
public class RngProbe
{
    static final class Q
    {
        int id; long t0; boolean gc; boolean closed;
        int batch; int cf, max, rq0, live, total, req, vn;
        int nResp, nBefore; long bytes, bytesBefore;
        long live0 = -1;
    }

    private static PrintWriter out;
    private static int seq = 0;
    private static final Map<Object, Q> byIter = new IdentityHashMap<>();
    private static final Map<Object, Q> byTime = new IdentityHashMap<>();
    private static Field dataField;
    private static Field capField;

    private static synchronized void emit(String s)
    {
        try
        {
            if (out == null)
                out = new PrintWriter(new FileWriter(System.getProperty("rng.out"), true), true);
            out.println(s);
        }
        catch (Exception e)
        {
            System.err.println("RngProbe emit failed: " + e);
        }
    }

    public static boolean isRng(Object c)
    {
        try
        {
            ReadCommand cmd = (ReadCommand) c;
            return "rng".equals(cmd.metadata().keyspace) && "t".equals(cmd.metadata().name);
        }
        catch (Throwable t)
        {
            return false;
        }
    }

    public static synchronized void begin(Object it, Object requestTime)
    {
        Q q = new Q();
        q.id = ++seq;
        q.t0 = System.nanoTime();
        String flag = System.getProperty("rng.flag");
        q.gc = flag != null && new java.io.File(flag).exists();
        byIter.put(it, q);
        byTime.put(requestTime, q);
        emit("BEGIN," + q.id + "," + System.currentTimeMillis() + ",gc=" + (q.gc ? 1 : 0));
    }

    public static void batchStart(Object it, int cf, int max, int rq0, int live, int total)
    {
        Q q;
        synchronized (RngProbe.class)
        {
            q = byIter.get(it);
            if (q == null) { emit("ERR,batchStart without BEGIN"); return; }
            q.batch++; q.cf = cf; q.max = max; q.rq0 = rq0; q.live = live; q.total = total; q.req = 0; q.vn = 0;
        }
        if (q.batch == 1 && q.gc)
            q.live0 = liveTotal();
    }

    public static synchronized void request(Object it, int vnodes, int contacts)
    {
        Q q = byIter.get(it);
        if (q == null) { emit("ERR,request without BEGIN"); return; }
        q.req++; q.vn += vnodes;
    }

    public static synchronized void batchEnd(Object it, int rq1, int br)
    {
        Q q = byIter.get(it);
        if (q == null) { emit("ERR,batchEnd without BEGIN"); return; }
        emit("BATCH," + q.id + "," + q.batch + ",cf=" + q.cf + ",max=" + q.max + ",rq0=" + q.rq0 + ",live=" + q.live + ",total=" + q.total
             + ",req=" + q.req + ",vn=" + q.vn + ",rq1=" + rq1 + ",br=" + br);
    }

    public static synchronized void response(Object requestTime, Object m)
    {
        Q q = byTime.get(requestTime);
        if (q == null) { emit("ERR,response without BEGIN"); return; }
        Message<?> msg = (Message<?>) m;
        long len = -1, rem = -1;
        String cls = msg.payload == null ? "null" : msg.payload.getClass().getSimpleName();
        try
        {
            if (dataField == null)
            {
                Class<?> dr = Class.forName("org.apache.cassandra.db.ReadResponse$DataResponse");
                dataField = dr.getDeclaredField("data");
                dataField.setAccessible(true);
            }
            if (msg.payload instanceof ReadResponse && dataField.getDeclaringClass().isInstance(msg.payload))
            {
                ByteBuffer b = (ByteBuffer) dataField.get(msg.payload);
                rem = b.remaining();
                len = b.hasArray() ? b.array().length : -b.capacity();
            }
        }
        catch (Throwable t)
        {
            emit("ERR,response " + t);
        }
        q.nResp++;
        if (len > 0) q.bytes += len;
        if (!q.closed)
        {
            q.nBefore++;
            if (len > 0) q.bytesBefore += len;
        }
        emit("RESP," + q.id + "," + ms(q) + "," + msg.from() + "," + len + "," + rem + "," + (q.closed ? 1 : 0) + "," + cls);
    }

    public static void close(Object it)
    {
        Q q;
        int nb; long hb;
        synchronized (RngProbe.class)
        {
            q = byIter.remove(it);
            if (q == null) { emit("ERR,close without BEGIN"); return; }
            q.closed = true;
            nb = q.nBefore; hb = q.bytesBefore;
        }
        long live1 = q.gc ? liveTotal() : -1;
        synchronized (RngProbe.class)
        {
            emit("CLOSE," + q.id + "," + ms(q) + ",cap=" + cap() + ",nb=" + nb + ",H=" + hb + ",gc=" + (q.gc ? 1 : 0) + ",live0=" + q.live0
                 + ",live1=" + live1 + ",nend=" + q.nResp + ",Hend=" + q.bytes);
        }
    }

    private static long ms(Q q)
    {
        return (System.nanoTime() - q.t0) / 1_000_000;
    }

    private static int cap()
    {
        try
        {
            if (capField == null)
            {
                capField = Class.forName("org.apache.cassandra.service.reads.range.RangeCommands").getDeclaredField("MAX_CONCURRENT_RANGE_REQUESTS");
                capField.setAccessible(true);
            }
            return capField.getInt(null);
        }
        catch (Throwable t)
        {
            emit("ERR,cap " + t);
            return -1;
        }
    }

    public static long liveTotal()
    {
        try
        {
            MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
            String r = (String) mbs.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                           new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
            for (String line : r.split("\n"))
            {
                String t = line.trim();
                if (t.startsWith("Total"))
                {
                    String[] f = t.split("\\s+");
                    return Long.parseLong(f[2]);
                }
            }
            emit("ERR,histogram without Total");
        }
        catch (Throwable t)
        {
            emit("ERR,histogram " + t);
        }
        return -2;
    }
}
