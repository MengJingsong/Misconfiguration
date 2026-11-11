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
 * Stage-4 harness, cluster tier B3d (amended 2026-10-24) of memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.
 * One JMX connection to 127.0.0.1:<port>; every 1 s appends
 *   epoch_ms,AllMemtablesOnHeapDataSize,BlockedOnAllocation Count,PendingFlushTasks,HeapMemoryUsage.used
 * to <csv> until <stopfile> exists.   usage: java Sampler <port> <csv> <stopfile>
 * (Pattern from the memtable_heap_space / memtable_offheap_space harnesses' Sampler.java.)
 */
public class Sampler
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        ObjectName on = new ObjectName("org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize");
        ObjectName blk = new ObjectName("org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation");
        ObjectName pend = new ObjectName("org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        File stop = new File(a[2]);
        try (JMXConnector c = JMXConnectorFactory.connect(u);
             PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("epoch_ms,on_heap_gauge_bytes,blocked_count,pending_flush_tasks,heap_used");
            long next = System.currentTimeMillis();
            while (!stop.exists())
            {
                long t = System.currentTimeMillis();
                String row;
                try
                {
                    row = t + "," + m.getAttribute(on, "Value") + "," + m.getAttribute(blk, "Count") + "," + m.getAttribute(pend, "Value")
                          + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used");
                }
                catch (Exception e)
                {
                    row = t + ",ERROR " + e.getClass().getSimpleName() + ",,,";
                }
                w.println(row);
                next += 1000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
