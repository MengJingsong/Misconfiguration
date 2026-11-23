// U13 stage-2 JMX sampler (design §2.6 item 1). usage: java Poll <jmx-port> <period-ms>
// One space-separated row per sample, header first; a metric that does not exist is -1.
// direct_* = java.nio:type=BufferPool,name=direct (MemoryUsed, TotalCapacity, Count); heap via MemoryMXBean;
// u13.t MemtableOnHeapDataSize / MemtableLiveDataSize / MemtableSwitchCount / PendingFlushes / BytesFlushed;
// MemtablePool PendingFlushTasks; Cassandra BufferPool chunk-cache and networking UsedSize/Size; GC counts/times.
import java.lang.management.*;
import java.util.*;
import javax.management.*;
import javax.management.remote.*;

public class Poll
{
    static MBeanServerConnection m;

    static long attr(String on, String a)
    {
        try { Object v = m.getAttribute(new ObjectName(on), a); return ((Number) v).longValue(); }
        catch (Exception e) { return -1; }
    }

    static long cv(String on)
    {
        long v = attr(on, "Count");
        return v != -1 ? v : attr(on, "Value");
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        long period = Long.parseLong(a[1]);
        String M = "org.apache.cassandra.metrics:";
        String t = M + "type=Table,keyspace=u13,scope=t,name=";
        String D = "java.nio:type=BufferPool,name=direct";
        String[][] cols = {
            {"t_onheap", t + "MemtableOnHeapDataSize"}, {"t_live", t + "MemtableLiveDataSize"},
            {"t_switch", t + "MemtableSwitchCount"}, {"t_pendflush", t + "PendingFlushes"}, {"t_bytesflushed", t + "BytesFlushed"},
            {"all_onheap", M + "type=Table,name=AllMemtablesOnHeapDataSize"},
            {"pool_pending", M + "type=MemtablePool,name=PendingFlushTasks"},
            {"bp_cc_used", M + "type=BufferPool,scope=chunk-cache,name=UsedSize"}, {"bp_cc_size", M + "type=BufferPool,scope=chunk-cache,name=Size"},
            {"bp_net_used", M + "type=BufferPool,scope=networking,name=UsedSize"}, {"bp_net_size", M + "type=BufferPool,scope=networking,name=Size"},
        };
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            m = c.getMBeanServerConnection();
            MemoryMXBean mem = ManagementFactory.newPlatformMXBeanProxy(m, ManagementFactory.MEMORY_MXBEAN_NAME, MemoryMXBean.class);
            List<GarbageCollectorMXBean> gcs = new ArrayList<>();
            for (ObjectName on : m.queryNames(new ObjectName(ManagementFactory.GARBAGE_COLLECTOR_MXBEAN_DOMAIN_TYPE + ",*"), null))
                gcs.add(ManagementFactory.newPlatformMXBeanProxy(m, on.toString(), GarbageCollectorMXBean.class));
            gcs.sort(Comparator.comparing(GarbageCollectorMXBean::getName));
            StringBuilder h = new StringBuilder("epoch_ms heap_used direct_used direct_cap direct_count");
            for (GarbageCollectorMXBean g : gcs) { String n = g.getName().replace(' ', '_'); h.append(' ').append(n).append("_n ").append(n).append("_ms"); }
            for (String[] col : cols) h.append(' ').append(col[0]);
            System.out.println(h);
            System.out.flush();
            while (true)
            {
                long t0 = System.currentTimeMillis();
                StringBuilder s = new StringBuilder();
                s.append(t0).append(' ').append(mem.getHeapMemoryUsage().getUsed())
                 .append(' ').append(attr(D, "MemoryUsed")).append(' ').append(attr(D, "TotalCapacity")).append(' ').append(attr(D, "Count"));
                for (GarbageCollectorMXBean g : gcs) s.append(' ').append(g.getCollectionCount()).append(' ').append(g.getCollectionTime());
                for (String[] col : cols) s.append(' ').append(cv(col[1]));
                System.out.println(s);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
