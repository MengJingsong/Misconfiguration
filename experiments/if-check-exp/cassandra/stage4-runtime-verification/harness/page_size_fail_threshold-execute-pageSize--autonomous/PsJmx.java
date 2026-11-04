/*
 * Stage-4 harness, cluster tier (B3, as amended 2026-10-26) of page_size_fail_threshold-execute-pageSize--autonomous.
 * A small JMX client for the node on 127.0.0.1:7199 (local JMX, no auth). It replaces `jstat` (cannot attach on this
 * host) and `nodetool sjk mx` (exits 0 on failure).
 *
 *   java PsJmx thresholds                  -> RESULT thresholds warn=<w> fail=<f>   (GuardrailsMBean getters)
 *   java PsJmx setpage <warn> <fail>       -> invokes setPageSizeThreshold(warn, fail), then prints the read-back
 *   java PsJmx rowsread                    -> RESULT rowsread count=<ClientRequestSize.RowsRead Count>; count=0 absent=true when the
 *                                             bean is not registered yet (its static counters, ClientRequestSizeMetrics.java:39-42,
 *                                             are created at class load, before any row is recorded)
 *   java PsJmx gc                          -> invokes java.lang:type=Memory gc() (System.gc(): a full G1 collection; no
 *                                             ExplicitGC flags in conf/), then prints heap used
 *   java PsJmx poll <out> <stopfile> <ms>  -> every <ms>: "<epoch ms> <heap used B> <heap committed B> <young GC count> <old GC count>"
 *                                             (java.lang:type=Memory HeapMemoryUsage = S0U+S1U+EU+OU of jstat), until <stopfile> exists
 */
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.MemoryUsage;
import java.util.Set;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class PsJmx
{
    static final String GR = "org.apache.cassandra.db:type=Guardrails";
    static final String RR = "org.apache.cassandra.metrics:type=ClientRequestSize,name=RowsRead";

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "thresholds":
                    printThr(m);
                    break;
                case "setpage":
                    m.invoke(new ObjectName(GR), "setPageSizeThreshold",
                             new Object[]{ Integer.parseInt(a[1]), Integer.parseInt(a[2]) },
                             new String[]{ "int", "int" });
                    printThr(m);
                    break;
                case "rowsread":
                    if (m.isRegistered(new ObjectName(RR)))
                        System.out.println("RESULT rowsread count=" + m.getAttribute(new ObjectName(RR), "Count"));
                    else
                        System.out.println("RESULT rowsread count=0 absent=true");
                    break;
                case "gc":
                    m.invoke(new ObjectName("java.lang:type=Memory"), "gc", null, null);
                    System.out.println("RESULT gc heap_used=" + MemoryUsage.from((CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")).getUsed());
                    break;
                case "poll":
                    poll(m, a[1], a[2], Long.parseLong(a[3]));
                    break;
                default:
                    throw new IllegalArgumentException(a[0]);
            }
        }
    }

    static void printThr(MBeanServerConnection m) throws Exception
    {
        ObjectName gr = new ObjectName(GR);
        System.out.println("RESULT thresholds warn=" + m.getAttribute(gr, "PageSizeWarnThreshold")
                           + " fail=" + m.getAttribute(gr, "PageSizeFailThreshold"));
    }

    static void poll(MBeanServerConnection m, String out, String stop, long ms) throws Exception
    {
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        ObjectName young = null, old = null;
        Set<ObjectName> gcs = m.queryNames(new ObjectName("java.lang:type=GarbageCollector,*"), null);
        for (ObjectName g : gcs)
        {
            String n = g.getKeyProperty("name");
            if (n.contains("Young")) young = g;
            else if (n.contains("Old")) old = g;
        }
        File sf = new File(stop);
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            w.println("# epoch_ms heap_used heap_committed young_gc old_gc  (young=" + young + " old=" + old + ")");
            while (!sf.exists())
            {
                long t = System.currentTimeMillis();
                MemoryUsage u = MemoryUsage.from((CompositeData) m.getAttribute(mem, "HeapMemoryUsage"));
                Object yc = young == null ? -1 : m.getAttribute(young, "CollectionCount");
                Object oc = old == null ? -1 : m.getAttribute(old, "CollectionCount");
                w.println(t + " " + u.getUsed() + " " + u.getCommitted() + " " + yc + " " + oc);
                w.flush();
                long sleep = ms - (System.currentTimeMillis() - t);
                if (sleep > 0) Thread.sleep(sleep);
            }
        }
    }
}
