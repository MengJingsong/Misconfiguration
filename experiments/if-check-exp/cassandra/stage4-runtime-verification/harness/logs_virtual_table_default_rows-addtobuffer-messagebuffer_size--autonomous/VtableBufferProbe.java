package org.apache.cassandra.db.virtual;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.List;
import javax.management.ObjectName;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.LoggingEvent;
import org.apache.cassandra.utils.logging.VirtualTableAppender;

/**
 * Stage-4 unit probe for logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous (B2).
 * usage: VtableBufferProbe appender <N> <payloadBytes>     -> pushes N events through VirtualTableAppender.doAppend
 *        VtableBufferProbe table <N> <payloadBytes>        -> pushes N events into LogMessagesTable (size = resolveBufferSize()),
 *                                                             and N events into an appender, in the same JVM (positive control)
 * Events are created on the fly and never retained by the probe. Message = "<seq>:" + padding.
 */
public class VtableBufferProbe
{
    static final LoggerContext ctx = new LoggerContext();

    static LoggingEvent event(long seq, int payload)
    {
        StringBuilder sb = new StringBuilder(payload + 12).append(seq).append(':');
        while (sb.length() < payload) sb.append('x');
        LoggingEvent e = new LoggingEvent("probe", ctx.getLogger("org.apache.cassandra.probe"), Level.WARN, sb.toString(), null, null);
        e.getFormattedMessage(); // resolve once, as the real table does
        return e;
    }

    static Object get(Object o, String f) throws Exception
    {
        Field fl = o.getClass().getDeclaredField(f);
        fl.setAccessible(true);
        return fl.get(o);
    }

    static long heap() throws Exception
    {
        long prev = -1, cur = 0;
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(100); }
        hist("java.lang.String"); // a full GC through the diagnostic command (clears soft refs), then read
        cur = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
        return cur;
    }

    /** count of live instances of a class via the in-process DiagnosticCommand gcClassHistogram (a full GC) */
    static long[] hist(String cls) throws Exception
    {
        ObjectName n = new ObjectName("com.sun.management:type=DiagnosticCommand");
        String out = (String) ManagementFactory.getPlatformMBeanServer().invoke(n, "gcClassHistogram", new Object[]{ new String[0] }, new String[]{ "[Ljava.lang.String;" });
        for (String l : out.split("\n"))
        {
            String[] p = l.trim().split("\\s+");
            if (p.length >= 4 && p[3].equals(cls)) return new long[]{ Long.parseLong(p[1]), Long.parseLong(p[2]) };
        }
        return new long[]{ 0, 0 };
    }

    static String seq(Object e)
    {
        String m = ((LoggingEvent) e).getFormattedMessage();
        return m.substring(0, m.indexOf(':'));
    }

    static void report(String tag, long base, long N, int payload, List<?> buf, boolean tableList) throws Exception
    {
        long h = heap();
        long[] hc = hist("ch.qos.logback.classic.spi.LoggingEvent");
        long[] lm = hist("org.apache.cassandra.db.virtual.LogMessagesTable$LogMessage");
        String first = "-", last = "-";
        if (!buf.isEmpty())
        {
            if (tableList)
            {
                first = Long.toString(Long.parseLong(((LogMessagesTable.LogMessage) buf.get(0)).message.split(":")[0]));
                last = Long.toString(Long.parseLong(((LogMessagesTable.LogMessage) buf.get(buf.size() - 1)).message.split(":")[0]));
            }
            else { first = seq(buf.get(0)); last = seq(buf.get(buf.size() - 1)); }
        }
        System.out.println("STAGE4 " + tag + " N=" + N + " payload=" + payload + " size=" + buf.size() + " firstSeq=" + first + " lastSeq=" + last
                           + " LoggingEventInstances=" + hc[0] + " LoggingEventBytes=" + hc[1] + " LogMessageInstances=" + lm[0]
                           + " heapUsedAfterGC=" + h + " heapDelta=" + (h - base));
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] a) throws Exception
    {
        String mode = a[0]; long N = Long.parseLong(a[1]); int payload = Integer.parseInt(a[2]);
        // warm-up: 1000 events through a throw-away appender, discarded
        VirtualTableAppender w = new VirtualTableAppender(); w.start();
        for (int i = 0; i < 1000; i++) w.doAppend(event(i, payload));
        w.stop();
        hist("java.lang.String"); hist("java.lang.String"); // warm the diagnostic-command path and settle the heap before the baseline
        long base = heap();
        System.out.println("STAGE4 baseline heapUsedAfterGC=" + base + " maxRowsProp=" + System.getProperty("cassandra.virtual.logs.max.rows"));
        if (mode.equals("appender") || mode.equals("table"))
        {
            VirtualTableAppender ap = new VirtualTableAppender(); ap.start();
            for (long i = 0; i < N; i++) ap.doAppend(event(i, payload));
            List<?> mb = (List<?>) get(ap, "messageBuffer");
            report("appender-after-push", base, N, payload, mb, false);
            if (mode.equals("table"))
            {
                int size = LogMessagesTable.resolveBufferSize();
                LogMessagesTable t = new LogMessagesTable("system_views", size);
                hist("java.lang.String");
                long base2 = heap();
                for (long i = 0; i < N; i++) t.add(event(i, payload));
                List<?> tb = (List<?>) get(t, "buffer");
                System.out.println("STAGE4 table resolveBufferSize=" + size);
                report("table-after-add", base2, N, payload, tb, true);
                // appender buffer is unaffected by the property: still the same size
                System.out.println("STAGE4 appender-size-in-table-JVM size=" + mb.size());
            }
            else
            {
                ap.stop();
                report("appender-after-stop", base, N, payload, mb, false);
            }
        }
        System.out.println("STAGE4 done");
    }
}
