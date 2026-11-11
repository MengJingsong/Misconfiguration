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
 * Stage-4 harness, cluster tier B3d (2)-(3) (amended 2026-10-25) of coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.
 * Replaces jstat (cannot attach on this host). Adapted from the memtable_heap_space autonomous harness's Sampler (copied, then changed).
 * One JMX connection to 127.0.0.1:<port>; every 1 s appends
 *   epoch_ms,heap_used,old_used,old_after_gc,coord_aborts,local_aborts,coord_max,local_max
 * to <csv> until <stopfile> exists. A metric that does not exist yet is left empty.   usage: java Sampler <port> <csv> <stopfile>
 */
public class Sampler
{
    static Object used(Object cd) { return cd == null ? "" : ((CompositeData) cd).get("used"); }

    static String get(MBeanServerConnection m, ObjectName on, String attr)
    {
        try { return String.valueOf(m.getAttribute(on, attr)); } catch (Exception e) { return ""; }
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        String t = "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=";
        ObjectName ca = new ObjectName(t + "CoordinatorReadSizeAborts"), la = new ObjectName(t + "LocalReadSizeAborts");
        ObjectName cm = new ObjectName(t + "CoordinatorReadSize"), lm = new ObjectName(t + "LocalReadSize");
        ObjectName old = new ObjectName("java.lang:type=MemoryPool,name=G1 Old Gen");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        File stop = new File(a[2]);
        try (JMXConnector c = JMXConnectorFactory.connect(u);
             PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("epoch_ms,heap_used,old_used,old_after_gc,coord_aborts,local_aborts,coord_max,local_max");
            long next = System.currentTimeMillis();
            while (!stop.exists())
            {
                long now = System.currentTimeMillis();
                String row;
                try
                {
                    row = now + "," + used(m.getAttribute(mem, "HeapMemoryUsage")) + "," + used(m.getAttribute(old, "Usage")) + ","
                          + used(m.getAttribute(old, "CollectionUsage")) + "," + get(m, ca, "Count") + "," + get(m, la, "Count") + ","
                          + get(m, cm, "Max") + "," + get(m, lm, "Max");
                }
                catch (Exception e) { row = now + ",ERROR " + e.getClass().getSimpleName() + ",,,,,,"; }
                w.println(row);
                next += 1000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
