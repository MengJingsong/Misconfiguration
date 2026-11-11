import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.util.Map;
import java.util.TreeMap;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.
 * Pattern of harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/CounterCacheSampler.java (one JMX
 * connection; jstat cannot attach here). Modes:
 *   sample <port> <csv> <phasefile> <stopfile>   every 5 s appends
 *     epoch_ms,phase,pool_size_bytes,capacity_mb,avg_interval,resize_min,own_bytes,live_sstables,heap_used
 *     (org.apache.cassandra.db:type=IndexSummaries MemoryPoolSizeInMB (x 2^20, rounded) / MemoryPoolCapacityInMB /
 *     AverageIndexInterval / ResizeIntervalInMinutes; org.apache.cassandra.metrics:type=Table,keyspace=keyspace1,scope=standard1,
 *     name=IndexSummaryOffHeapMemoryUsed|LiveSSTableCount (Value); java.lang:type=Memory HeapMemoryUsage.used) until <stopfile> exists.
 *   attrs <port>                                  prints the IndexSummaries attributes once (read-back).
 *   invoke <port>                                 prints attributes, invokes redistributeSummaries() (synchronous), prints the
 *                                                 call's duration, attributes and the IndexIntervals map afterwards (R1).
 *   intervals <port>                              prints the attributes and the IndexIntervals map.
 */
public class ISSampler
{
    static final String ISM = "org.apache.cassandra.db:type=IndexSummaries";
    static final String TBL = "org.apache.cassandra.metrics:type=Table,keyspace=keyspace1,scope=standard1,name=";

    static String attrs(MBeanServerConnection m) throws Exception
    {
        ObjectName n = new ObjectName(ISM);
        double mb = (Double) m.getAttribute(n, "MemoryPoolSizeInMB");
        String own;
        try
        {
            own = String.valueOf(m.getAttribute(new ObjectName(TBL + "IndexSummaryOffHeapMemoryUsed"), "Value"));
        }
        catch (Exception e)
        {
            own = "n/a";
        }
        return "pool_size_bytes=" + Math.round(mb * 1024 * 1024) + " capacity_mb=" + m.getAttribute(n, "MemoryPoolCapacityInMB")
               + " avg_interval=" + m.getAttribute(n, "AverageIndexInterval") + " resize_min=" + m.getAttribute(n, "ResizeIntervalInMinutes")
               + " own_bytes=" + own;
    }

    @SuppressWarnings("unchecked")
    static void intervals(MBeanServerConnection m) throws Exception
    {
        Map<String, Integer> iv = new TreeMap<>((Map<String, Integer>) m.getAttribute(new ObjectName(ISM), "IndexIntervals"));
        for (Map.Entry<String, Integer> e : iv.entrySet())
            System.out.println("INTERVAL " + e.getValue() + " " + e.getKey());
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "attrs":
                    System.out.println("ATTRS " + System.currentTimeMillis() + " " + attrs(m));
                    return;
                case "intervals":
                    System.out.println("ATTRS " + System.currentTimeMillis() + " " + attrs(m));
                    intervals(m);
                    return;
                case "invoke":
                {
                    System.out.println("BEFORE " + System.currentTimeMillis() + " " + attrs(m));
                    long t0 = System.currentTimeMillis();
                    m.invoke(new ObjectName(ISM), "redistributeSummaries", null, null);
                    long t1 = System.currentTimeMillis();
                    System.out.println("INVOKED redistributeSummaries start=" + t0 + " end=" + t1 + " ms=" + (t1 - t0));
                    System.out.println("AFTER " + t1 + " " + attrs(m));
                    intervals(m);
                    return;
                }
                case "sample":
                    break;
                default:
                    throw new IllegalArgumentException(a[0]);
            }
            ObjectName ism = new ObjectName(ISM), own = new ObjectName(TBL + "IndexSummaryOffHeapMemoryUsed"),
                       cnt = new ObjectName(TBL + "LiveSSTableCount"), mem = new ObjectName("java.lang:type=Memory");
            File phase = new File(a[3]), stop = new File(a[4]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[2], true), true))
            {
                w.println("epoch_ms,phase,pool_size_bytes,capacity_mb,avg_interval,resize_min,own_bytes,live_sstables,heap_used");
                long next = System.currentTimeMillis();
                while (true)
                {
                    boolean last = stop.exists();
                    long t = System.currentTimeMillis();
                    String ph = phase.exists() ? new String(Files.readAllBytes(phase.toPath())).trim() : "";
                    String row;
                    try
                    {
                        double mb = (Double) m.getAttribute(ism, "MemoryPoolSizeInMB");
                        String o, k;
                        try { o = String.valueOf(m.getAttribute(own, "Value")); k = String.valueOf(m.getAttribute(cnt, "Value")); }
                        catch (Exception e) { o = ""; k = ""; }
                        row = t + "," + ph + "," + Math.round(mb * 1024 * 1024) + "," + m.getAttribute(ism, "MemoryPoolCapacityInMB")
                              + "," + m.getAttribute(ism, "AverageIndexInterval") + "," + m.getAttribute(ism, "ResizeIntervalInMinutes")
                              + "," + o + "," + k + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used");
                    }
                    catch (Exception e)
                    {
                        row = t + "," + ph + ",ERROR " + e.getClass().getSimpleName() + ",,,,,,";
                    }
                    w.println(row);
                    if (last) break;
                    next += 5000;
                    long sl = next - System.currentTimeMillis();
                    if (sl > 0) Thread.sleep(sl);
                }
            }
        }
    }
}
