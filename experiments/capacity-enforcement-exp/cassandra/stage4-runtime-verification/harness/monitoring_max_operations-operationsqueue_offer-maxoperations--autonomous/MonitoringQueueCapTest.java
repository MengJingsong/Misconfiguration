/*
 * Stage 4, unit tier (B2) of monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/db/monitoring/ of a copy of cassandra-5.0.9 and run:
 *   ant testsome -Dtest.name=org.apache.cassandra.db.monitoring.MonitoringQueueCapTest \
 *     -Dtest.jvm.args="-Dstage4.out=<file> -Dstage4.m=<M adds per queue> -Dstage4.ns=0,1,50,1000,-1 -Dstage4.rep=<r>"
 * For each N in stage4.ns: MonitoringTask.make(3600000, N), then M addFailedOperation and M addSlowOperation of distinct stub
 * Monitorables each holding a 1 KiB byte[]. Reads: the queues' own sizes (reflection), the instance counts of the two Operation
 * classes and of the stub class from a GC.class_histogram (DiagnosticCommand, forces a full GC), live heap after GC against the
 * pre-load baseline, then the drain (getFailedOperations / getSlowOperations) with the dropped count parsed from the message.
 */
package org.apache.cassandra.db.monitoring;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.Test;

import static org.apache.cassandra.utils.Clock.Global.nanoTime;

public class MonitoringQueueCapTest
{
    static PrintWriter out;

    static synchronized void line(String s)
    {
        System.out.println(s);
        try
        {
            if (out == null && System.getProperty("stage4.out") != null)
                out = new PrintWriter(new FileWriter(System.getProperty("stage4.out"), true), true);
        }
        catch (java.io.IOException e)
        {
            throw new RuntimeException(e);
        }
        if (out != null)
            out.println(s);
    }

    static final class Stub extends MonitorableImpl
    {
        final String name;
        final byte[] payload = new byte[1024];

        Stub(String name)
        {
            this.name = name;
            setMonitoringTime(nanoTime(), false, 1_000_000_000L, 1_000_000_000L);
        }

        public String name()
        {
            return name;
        }
    }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++)
        {
            System.gc();
            Thread.sleep(300);
        }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static String histogram() throws Exception
    {
        MBeanServer mb = ManagementFactory.getPlatformMBeanServer();
        return (String) mb.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                  new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
    }

    static long[] inst(String histo, String cls)
    {
        Matcher m = Pattern.compile("^\\s*\\d+:\\s+(\\d+)\\s+(\\d+)\\s+" + Pattern.quote(cls) + "\\s*$", Pattern.MULTILINE).matcher(histo);
        return m.find() ? new long[]{ Long.parseLong(m.group(1)), Long.parseLong(m.group(2)) } : new long[]{ 0, 0 };
    }

    static int queueSize(Object task, String field) throws Exception
    {
        Field f = MonitoringTask.class.getDeclaredField(field);
        f.setAccessible(true);
        Object oq = f.get(task);
        Field q = oq.getClass().getDeclaredField("queue");
        q.setAccessible(true);
        return ((BlockingQueue<?>) q.get(oq)).size();
    }

    static long dropped(List<String> msg)
    {
        Pattern p = Pattern.compile("\\((\\d+) were dropped\\)");
        for (String s : msg)
        {
            Matcher m = p.matcher(s);
            if (m.find())
                return Long.parseLong(m.group(1));
        }
        return 0;
    }

    @Test
    public void run() throws Throwable
    {
        int m = Integer.parseInt(System.getProperty("stage4.m", "10000"));
        String rep = System.getProperty("stage4.rep", "1");
        for (String ns : System.getProperty("stage4.ns", "0,1,50,1000,-1").split(","))
        {
            int n = Integer.parseInt(ns.trim());
            MonitoringTask.instance = MonitoringTask.make(3600000, n);
            MonitoringTask t = MonitoringTask.instance;
            long h0 = usedAfterGc();
            long a0 = ManagementFactory.getThreadMXBean() instanceof com.sun.management.ThreadMXBean
                      ? ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId()) : -1;
            for (int i = 0; i < m; i++)
            {
                MonitoringTask.addFailedOperation(new Stub("f" + i), nanoTime());
                MonitoringTask.addSlowOperation(new Stub("s" + i), nanoTime());
            }
            long a1 = ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
            int qf = queueSize(t, "failedOperationsQueue"), qs = queueSize(t, "slowOperationsQueue");
            long h1 = usedAfterGc();
            String hist = histogram();
            long[] fo = inst(hist, "org.apache.cassandra.db.monitoring.MonitoringTask$FailedOperation");
            long[] so = inst(hist, "org.apache.cassandra.db.monitoring.MonitoringTask$SlowOperation");
            long[] st = inst(hist, "org.apache.cassandra.db.monitoring.MonitoringQueueCapTest$Stub");
            List<String> fm = t.getFailedOperations();
            List<String> sm = t.getSlowOperations();
            long dropF = dropped(fm), dropS = dropped(sm);
            int linesF = fm.size() - (dropF > 0 ? 1 : 0);
            long h2 = usedAfterGc();
            line("STAGE4 final rep=" + rep + " N=" + n + " M=" + m + " queueFailed=" + qf + " queueSlow=" + qs
                 + " FailedOperation_instances=" + fo[0] + " FailedOperation_bytes=" + fo[1] + " SlowOperation_instances=" + so[0] + " SlowOperation_bytes=" + so[1]
                 + " Stub_instances=" + st[0] + " Stub_bytes=" + st[1] + " liveHeapBefore=" + h0 + " liveHeapLoaded=" + h1 + " liveDelta=" + (h1 - h0)
                 + " droppedFailed=" + dropF + " droppedSlow=" + dropS + " failedLogLines=" + linesF + " liveAfterDrain=" + h2 + " allocMB=" + (a1 - a0) / 1048576);
            t.cancel();
        }
        line("STAGE4 done rep=" + rep);
    }
}
