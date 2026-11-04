/*
 * Stage-4 harness, cluster tier (B3, as amended 2026-10-26) of sai_vector_search_max_top_k-execute-pageSize--autonomous.
 * A small JMX client for the node on 127.0.0.1:7199 (local JMX, no auth). It replaces `jstat` (cannot attach on this host).
 *
 *   java TkJmx gc                          -> invokes java.lang:type=Memory gc() (System.gc(): a full G1 collection), prints heap used
 *   java TkJmx sysprop                     -> RESULT sysprop max_top_k=<value of -Dcassandra.sai.vector_search.max_top_k in the
 *                                             runtime MXBean's InputArguments, or none>
 *   java TkJmx poll <out> <stopfile> <ms>  -> every <ms>: "<epoch ms> <heap used B> <heap committed B> <young GC count> <old GC count>"
 *                                             (HeapMemoryUsage = S0U+S1U+EU+OU of jstat), until <stopfile> exists
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

public class TkJmx
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            ObjectName mem = new ObjectName("java.lang:type=Memory");
            switch (a[0])
            {
                case "gc":
                    m.invoke(mem, "gc", null, null);
                    System.out.println("RESULT gc heap_used=" + MemoryUsage.from((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).getUsed());
                    break;
                case "sysprop":
                    String v = "none";
                    for (String arg : (String[]) m.getAttribute(new ObjectName("java.lang:type=Runtime"), "InputArguments"))
                        if (arg.startsWith("-Dcassandra.sai.vector_search.max_top_k="))
                            v = arg.substring(arg.indexOf('=') + 1);
                    System.out.println("RESULT sysprop max_top_k=" + v);
                    break;
                case "poll":
                    poll(m, a[1], a[2], Long.parseLong(a[3]));
                    break;
                default:
                    throw new IllegalArgumentException(a[0]);
            }
        }
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
