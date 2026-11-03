/*
 * Stage-4 harness, cluster tier (B3, as amended 2026-10-26) of SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.
 * A small JMX client for the node on 127.0.0.1:7199 (local JMX, no auth). It replaces `nodetool sjk mx` (exits 0 on failure)
 * and `jstat` (cannot attach on this host).
 *
 *   java DpJmx counts                      -> RESULT counts coord_reads=<ClientRequest,scope=Read,name=Latency Count>
 *                                             table_coord_reads=<Table,keyspace=g,scope=t,name=CoordinatorReadLatency Count>
 *                                             (updated once per StorageProxy.read of a g.t command, StorageProxy.java:2056-2057)
 *                                             local_reads=<Table,keyspace=g,scope=t,name=ReadLatency Count> (absent -> -1)
 *   java DpJmx gc                          -> invokes java.lang:type=Memory gc() (System.gc(): a full G1 collection), then
 *                                             prints heap used after it
 *   java DpJmx poll <out> <stopfile> <ms>  -> every <ms>: "<epoch ms> <heap used B> <heap committed B> <young GC count> <old GC count>"
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

public class DpJmx
{
    static final String CR = "org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Latency";
    static final String TR = "org.apache.cassandra.metrics:type=Table,keyspace=g,scope=t,name=ReadLatency";
    static final String TC = "org.apache.cassandra.metrics:type=Table,keyspace=g,scope=t,name=CoordinatorReadLatency";

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "counts":
                    System.out.println("RESULT counts coord_reads=" + count(m, CR) + " table_coord_reads=" + count(m, TC) + " local_reads=" + count(m, TR));
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

    static long count(MBeanServerConnection m, String name) throws Exception
    {
        ObjectName on = new ObjectName(name);
        if (!m.isRegistered(on))
            return -1;
        return ((Number) m.getAttribute(on, "Count")).longValue();
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
