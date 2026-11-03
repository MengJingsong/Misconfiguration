import java.util.Map;
import java.util.TreeMap;

import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-26) of min_index_interval-validate-minIndexInterval--autonomous.
 * Pattern of harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/ISSampler.java (one JMX
 * connection; jstat and jmxterm are not usable on this host). Modes:
 *   snap <port> <label>     one line "SNAP <epoch_ms> <label> pool_size_bytes=.. capacity_mb=.. avg_interval=.. resize_min=..",
 *                           one line "GAUGE <ks> <IndexSummaryOffHeapMemoryUsed>" per keyspace ii_1, ii_16, ii_128, ii_512, ii_m512,
 *                           and one line "INTERVAL <effective interval> <sstable filename>" per live sstable (IndexIntervals map).
 *   setcap <port> <MB>      sets org.apache.cassandra.db:type=IndexSummaries MemoryPoolCapacityInMB and prints it back.
 */
public class MiiProbe
{
    static final String ISM = "org.apache.cassandra.db:type=IndexSummaries";
    static final String[] KS = { "ii_1", "ii_16", "ii_128", "ii_512", "ii_m512" };

    static String attrs(MBeanServerConnection m) throws Exception
    {
        ObjectName n = new ObjectName(ISM);
        double mb = (Double) m.getAttribute(n, "MemoryPoolSizeInMB");
        return "pool_size_bytes=" + Math.round(mb * 1024 * 1024) + " capacity_mb=" + m.getAttribute(n, "MemoryPoolCapacityInMB")
               + " avg_interval=" + m.getAttribute(n, "AverageIndexInterval") + " resize_min=" + m.getAttribute(n, "ResizeIntervalInMinutes");
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "snap":
                {
                    System.out.println("SNAP " + System.currentTimeMillis() + " " + a[2] + " " + attrs(m));
                    for (String ks : KS)
                    {
                        String v;
                        try
                        {
                            v = String.valueOf(m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Table,keyspace=" + ks
                                                                             + ",scope=standard1,name=IndexSummaryOffHeapMemoryUsed"), "Value"));
                        }
                        catch (Exception e)
                        {
                            v = "n/a";
                        }
                        System.out.println("GAUGE " + ks + " " + v);
                    }
                    Map<String, Integer> iv = new TreeMap<>((Map<String, Integer>) m.getAttribute(new ObjectName(ISM), "IndexIntervals"));
                    for (Map.Entry<String, Integer> e : iv.entrySet())
                        System.out.println("INTERVAL " + e.getValue() + " " + e.getKey());
                    return;
                }
                case "setcap":
                {
                    ObjectName n = new ObjectName(ISM);
                    System.out.println("BEFORE " + System.currentTimeMillis() + " " + attrs(m));
                    m.setAttribute(n, new Attribute("MemoryPoolCapacityInMB", Long.parseLong(a[2])));
                    System.out.println("SETCAP " + System.currentTimeMillis() + " requested=" + a[2] + " readback=" + m.getAttribute(n, "MemoryPoolCapacityInMB"));
                    System.out.println("AFTER " + System.currentTimeMillis() + " " + attrs(m));
                    return;
                }
                default:
                    throw new IllegalArgumentException(a[0]);
            }
        }
    }
}
