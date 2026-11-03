import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier (B3d as amended C4, 2026-10-27) of memtable_heap_space-LeafBuilder-allocated--autonomous.
 * Adapted from harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/Sampler.java (one JMX connection,
 * fixed-period rows); the metrics and the one-shot mode are this case's.
 *
 *   java Sampler loop <port> <csv> <stopfile> <period_ms>
 *     appends epoch_ms,t_all_on,t_cur_on,t_switch,g_all_on,blocked,pending_flush,heap_used every period until stopfile exists
 *       t_all_on  = metrics:type=Table,keyspace=ks,scope=t,name=AllMemtablesOnHeapDataSize  Value (all memtables of ks.t)
 *       t_cur_on  = ...,name=MemtableOnHeapDataSize Value (current memtable of ks.t)
 *       t_switch  = ...,name=MemtableSwitchCount Count
 *       g_all_on  = metrics:type=Table,name=AllMemtablesOnHeapDataSize Value (all tables)
 *       blocked   = metrics:type=MemtablePool,name=BlockedOnAllocation Count
 *       pending_flush = metrics:type=MemtablePool,name=PendingFlushTasks Value
 *       heap_used = java.lang:type=Memory HeapMemoryUsage.used
 *   java Sampler once <port>
 *     prints one line "ONCE <same columns>" and exits
 */
public class Sampler
{
    static final String T = "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=";

    static String row(MBeanServerConnection m) throws Exception
    {
        Object heap = ((CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")).get("used");
        return System.currentTimeMillis()
               + "," + m.getAttribute(new ObjectName(T + "AllMemtablesOnHeapDataSize"), "Value")
               + "," + m.getAttribute(new ObjectName(T + "MemtableOnHeapDataSize"), "Value")
               + "," + m.getAttribute(new ObjectName(T + "MemtableSwitchCount"), "Count")
               + "," + m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize"), "Value")
               + "," + m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation"), "Count")
               + "," + m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks"), "Value")
               + "," + heap;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("once"))
            {
                System.out.println("ONCE " + row(m));
                return;
            }
            File stop = new File(a[3]);
            long period = Long.parseLong(a[4]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[2], true), true))
            {
                w.println("epoch_ms,t_all_on,t_cur_on,t_switch,g_all_on,blocked,pending_flush,heap_used");
                long next = System.currentTimeMillis();
                while (!stop.exists())
                {
                    String r;
                    try
                    {
                        r = row(m);
                    }
                    catch (Exception e)
                    {
                        r = System.currentTimeMillis() + ",ERROR " + e.getClass().getSimpleName() + ",,,,,,";
                    }
                    w.println(r);
                    next += period;
                    long sl = next - System.currentTimeMillis();
                    if (sl > 0) Thread.sleep(sl);
                }
            }
        }
    }
}
