// 3-b confirm C4 diagnostic (admin JMX, not an attacker step): print the IndexSummaries pool, per-table summary bytes for
// atk.t1 / atk.tmax and the IndexIntervals of atk sstables; invoke redistributeSummaries(); print them again.  ISRedist <jmxport>
import java.util.*;
import javax.management.*;
import javax.management.remote.*;
public class ISRedist {
    static void show(MBeanServerConnection m, String tag) throws Exception {
        ObjectName n = new ObjectName("org.apache.cassandra.db:type=IndexSummaries");
        System.out.println(tag + " pool_MB=" + m.getAttribute(n, "MemoryPoolSizeInMB") + " capacity_MB=" + m.getAttribute(n, "MemoryPoolCapacityInMB") + " avg_interval=" + m.getAttribute(n, "AverageIndexInterval"));
        for (String t : new String[]{"t1", "tmax"})
            System.out.println(tag + " atk." + t + " summary_bytes=" + m.getAttribute(new ObjectName("org.apache.cassandra.metrics:type=Table,keyspace=atk,scope=" + t + ",name=IndexSummaryOffHeapMemoryUsed"), "Value"));
        @SuppressWarnings("unchecked") Map<String, Integer> iv = new TreeMap<>((Map<String, Integer>) m.getAttribute(n, "IndexIntervals"));
        for (Map.Entry<String, Integer> e : iv.entrySet()) if (e.getKey().contains("/atk/")) System.out.println(tag + " interval " + e.getValue() + " " + e.getKey().replaceAll(".*/atk/", "atk/"));
    }
    public static void main(String[] a) throws Exception {
        try (JMXConnector jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi"))) {
            MBeanServerConnection m = jc.getMBeanServerConnection();
            show(m, "BEFORE");
            long t0 = System.currentTimeMillis();
            m.invoke(new ObjectName("org.apache.cassandra.db:type=IndexSummaries"), "redistributeSummaries", null, null);
            System.out.println("redistributeSummaries took " + (System.currentTimeMillis() - t0) + " ms");
            show(m, "AFTER");
        }
    }
}
