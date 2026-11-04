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
 * Stage-4 harness, cluster tier B3d (amended 2026-10-24) of memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.
 * One JMX connection to 127.0.0.1:<port>; every 1 s appends
 *   epoch_ms,AllMemtablesOnHeapDataSize,AllMemtablesOffHeapDataSize,BlockedOnAllocationCount,
 *   G1 Old Gen Usage.used, G1 Old Gen CollectionUsage.used, HeapMemoryUsage.used   (columns 5-7: runbook fix 2026-10-24, replaces jstat)
 * to <csv> until <stopfile> exists.   usage: java Sampler <port> <csv> <stopfile>
 */
public class Sampler
{
    static Object used(Object cd)
    {
        return cd == null ? "" : ((CompositeData) cd).get("used");
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        ObjectName on = new ObjectName("org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize");
        ObjectName off = new ObjectName("org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize");
        ObjectName blk = new ObjectName("org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation");
        ObjectName old = new ObjectName("java.lang:type=MemoryPool,name=G1 Old Gen");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        File stop = new File(a[2]);
        try (JMXConnector c = JMXConnectorFactory.connect(u);
             PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("epoch_ms,on_heap_bytes,off_heap_bytes,blocked_count,old_used,old_after_gc,heap_used");
            long next = System.currentTimeMillis();
            while (!stop.exists())
            {
                long t = System.currentTimeMillis();
                String row;
                try
                {
                    row = t + "," + m.getAttribute(on, "Value") + "," + m.getAttribute(off, "Value") + "," + m.getAttribute(blk, "Count")
                          + "," + used(m.getAttribute(old, "Usage")) + "," + used(m.getAttribute(old, "CollectionUsage"))
                          + "," + used(m.getAttribute(mem, "HeapMemoryUsage"));
                }
                catch (Exception e)
                {
                    row = t + ",ERROR " + e.getClass().getSimpleName() + ",,,,,";
                }
                w.println(row);
                next += 1000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
