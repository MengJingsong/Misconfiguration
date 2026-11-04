package org.apache.cassandra.db.virtual;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.management.ObjectName;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.LoggingEvent;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;

/**
 * Stage-4 unit-tier probe for virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous (case B2).
 * Run through JUnitCore, one JVM per mode. System properties:
 *   probe.mode = cap | resolve      probe.out = output file (one "key=value ..." line per reading)
 *   mode cap:     probe.sizes = comma list of constructor sizes; probe.extra = adds beyond size (default 5000);
 *                 probe.len = message length in chars (default 200); probe.mult = adds = mult*size when set
 *   mode resolve: reads cassandra.virtual.logs.max.rows as given on the command line (-D) or from probe.props
 *                 (comma list of values, "unset" = clear) set in-process; prints LogMessagesTable.resolveBufferSize().
 * The table is built with the package-private LogMessagesTable(String,int) and fed through add(LoggingEvent), the method the
 * production appender calls. Row count is read three ways: buffer.size() (reflection), data() rows, and the live-instance
 * count of LogMessagesTable$LogMessage in a collecting class histogram (DiagnosticCommand gcClassHistogram).
 */
public class VirtualLogsMaxRowsProbeTest
{
    static PrintWriter out;

    static void log(String s)
    {
        out.println(s);
        out.flush();
        System.out.println("PROBE " + s);
    }

    /** class name -> {instances, bytes} from a collecting (live) class histogram of this JVM. */
    static Map<String, long[]> histo() throws Exception
    {
        String h = (String) ManagementFactory.getPlatformMBeanServer().invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"),
                                                                              "gcClassHistogram", new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        Map<String, long[]> m = new HashMap<>();
        for (String l : h.split("\n"))
        {
            String[] p = l.trim().split("\\s+");
            if (p.length >= 4 && p[0].endsWith(":"))
                m.put(p[3], new long[]{ Long.parseLong(p[1]), Long.parseLong(p[2]) });
        }
        return m;
    }

    static long g(Map<String, long[]> m, String k, int i)
    {
        long[] v = m.get(k);
        return v == null ? 0 : v[i];
    }

    static final String[] KEYS = { "org.apache.cassandra.db.virtual.LogMessagesTable$LogMessage", "java.util.LinkedList$Node", "java.lang.String", "[B" };

    @SuppressWarnings("unchecked")
    static List<Object> buffer(LogMessagesTable t) throws Exception
    {
        Field f = LogMessagesTable.class.getDeclaredField("buffer");
        f.setAccessible(true);
        return (List<Object>) f.get(t);
    }

    static String msg(long i, int len)
    {
        StringBuilder sb = new StringBuilder("m").append(i).append('-');
        while (sb.length() < len)
            sb.append('x');
        return sb.substring(0, len);
    }

    static String idOf(Object logMessage) throws Exception
    {
        Field f = LogMessagesTable.LogMessage.class.getField("message");
        String m = (String) f.get(logMessage);
        return m.substring(1, m.indexOf('-'));
    }

    static long dataRows(LogMessagesTable t)
    {
        long n = 0;
        try (org.apache.cassandra.db.partitions.UnfilteredPartitionIterator pi =
             t.select(org.apache.cassandra.db.DataRange.allData(t.metadata().partitioner), org.apache.cassandra.db.filter.ColumnFilter.all(t.metadata())))
        {
            while (pi.hasNext())
                try (org.apache.cassandra.db.rows.UnfilteredRowIterator ri = pi.next())
                {
                    while (ri.hasNext()) { ri.next(); n++; }
                }
        }
        return n;
    }

    @Test
    public void probe() throws Exception
    {
        out = new PrintWriter(new FileWriter(System.getProperty("probe.out")));
        DatabaseDescriptor.daemonInitialization();
        String mode = System.getProperty("probe.mode", "cap");
        if (mode.equals("resolve"))
        {
            String props = System.getProperty("probe.props");
            if (props == null)
                log("resolve source=-D value=" + System.getProperty("cassandra.virtual.logs.max.rows") + " resolved=" + LogMessagesTable.resolveBufferSize());
            else
                for (String v : props.split(","))
                {
                    if (v.equals("unset")) System.clearProperty("cassandra.virtual.logs.max.rows"); else System.setProperty("cassandra.virtual.logs.max.rows", v);
                    log("resolve source=in-process value=" + v + " resolved=" + LogMessagesTable.resolveBufferSize());
                }
            out.close();
            return;
        }
        if (mode.equals("mt"))
        {
            // 8 appender threads add concurrently (the production appender is called by every logging thread)
            final int size = Integer.parseInt(System.getProperty("probe.sizes")), per = Integer.getInteger("probe.per", 200000);
            final LogMessagesTable t = new LogMessagesTable("system_views", size);
            final LoggerContext c2 = new LoggerContext();
            Thread[] ts = new Thread[8];
            final java.util.concurrent.atomic.AtomicInteger maxSeen = new java.util.concurrent.atomic.AtomicInteger();
            for (int k = 0; k < ts.length; k++)
            {
                final int kk = k;
                ts[k] = new Thread(() -> {
                    ch.qos.logback.classic.Logger l = c2.getLogger("probe.t" + kk);
                    for (int i = 1; i <= per; i++)
                    {
                        t.add(new LoggingEvent("probe", l, Level.INFO, "m" + i + "-t" + kk, null, null));
                        if ((i & 1023) == 0)
                            try { maxSeen.accumulateAndGet(buffer(t).size(), Math::max); } catch (Exception e) { throw new RuntimeException(e); }
                    }
                });
                ts[k].start();
            }
            for (Thread th : ts) th.join();
            log("RESULT mt size=" + size + " threads=8 addsPerThread=" + per + " totalAdds=" + (8L * per) + " finalBufferSize=" + buffer(t).size() + " maxSampledBufferSize=" + maxSeen.get() + " dataRows=" + dataRows(t));
            out.close();
            return;
        }
        int len = Integer.getInteger("probe.len", 200);
        int extra = Integer.getInteger("probe.extra", 5000);
        Integer mult = Integer.getInteger("probe.mult");
        LoggerContext ctx = new LoggerContext();
        ch.qos.logback.classic.Logger lg = ctx.getLogger("probe.logger");
        for (String sz : System.getProperty("probe.sizes").split(","))
        {
            int size = Integer.parseInt(sz);
            long adds = mult != null ? (long) mult * size : size + extra;
            Runtime rt = Runtime.getRuntime();
            for (int i = 0; i < 3; i++) System.gc();
            Map<String, long[]> h0 = histo();
            long used0 = rt.totalMemory() - rt.freeMemory();
            LogMessagesTable t = new LogMessagesTable("system_views", size);
            // adds in checkpoints: size-1, size, size+1, then the rest
            long[] cps = { Math.max(1, size - 1), size, size + 1, adds };
            long done = 0;
            for (long cp : cps)
            {
                if (cp > adds || cp <= done) continue;
                while (done < cp)
                {
                    done++;
                    t.add(new LoggingEvent("probe", lg, Level.INFO, msg(done, len), null, null));
                }
                List<Object> b = buffer(t);
                log("size=" + size + " len=" + len + " adds=" + done + " bufferSize=" + b.size() + " newestId=" + idOf(b.get(0)) + " oldestId=" + idOf(b.get(b.size() - 1)));
            }
            long rows = dataRows(t);
            for (int i = 0; i < 3; i++) System.gc();
            Map<String, long[]> h1 = histo();
            long used1 = rt.totalMemory() - rt.freeMemory();
            long bytes = 0;
            StringBuilder sb = new StringBuilder();
            for (String k : KEYS)
            {
                long di = g(h1, k, 0) - g(h0, k, 0), db = g(h1, k, 1) - g(h0, k, 1);
                bytes += db;
                sb.append(' ').append(k.substring(k.lastIndexOf('.') + 1)).append("Inst=").append(di).append(' ').append(k.substring(k.lastIndexOf('.') + 1)).append("Bytes=").append(db);
            }
            log("RESULT size=" + size + " len=" + len + " adds=" + adds + " dataRows=" + rows + " bufferSize=" + buffer(t).size()
                + " logMessageInstances=" + g(h1, KEYS[0], 0) + sb + " sumBytes=" + bytes + " bytesPerRow=" + (rows == 0 ? 0 : bytes / rows)
                + " heapUsedDelta=" + (used1 - used0));
            t.truncate();
            log("truncate size=" + size + " bufferSize=" + buffer(t).size());
            t = null;
        }
        out.close();
    }
}
