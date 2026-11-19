// U11 stage-2 poller (extends stage-4 HeapPoll.java): heap pools, Old Gen collection usage, GC MXBeans, memtable
// counters (K), MutationStage multiplicity (A), every <period> ms over JMX (jstat cannot attach: PerfDisableSharedMem).
// usage: java Poll <jmx-port> <period-ms> <keyspace> <table>
// one line per sample (space-separated, header first); a metric that does not exist yet is -1.
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

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        long period = Long.parseLong(a[1]);
        String ks = a[2], tb = a[3];
        String tm = "org.apache.cassandra.metrics:type=Table,keyspace=" + ks + ",scope=" + tb + ",name=";
        String tp = "org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=";
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            m = c.getMBeanServerConnection();
            Map<String, MemoryPoolMXBean> pools = new HashMap<>();
            for (ObjectName on : m.queryNames(new ObjectName(ManagementFactory.MEMORY_POOL_MXBEAN_DOMAIN_TYPE + ",*"), null))
            {
                MemoryPoolMXBean p = ManagementFactory.newPlatformMXBeanProxy(m, on.toString(), MemoryPoolMXBean.class);
                pools.put(p.getName(), p);
            }
            List<GarbageCollectorMXBean> gcs = new ArrayList<>();
            for (ObjectName on : m.queryNames(new ObjectName(ManagementFactory.GARBAGE_COLLECTOR_MXBEAN_DOMAIN_TYPE + ",*"), null))
                gcs.add(ManagementFactory.newPlatformMXBeanProxy(m, on.toString(), GarbageCollectorMXBean.class));
            gcs.sort(Comparator.comparing(GarbageCollectorMXBean::getName));
            StringBuilder h = new StringBuilder("epoch_ms eden surv old old_coll");
            for (GarbageCollectorMXBean g : gcs) { String n = g.getName().replace(' ', '_'); h.append(' ').append(n).append("_n ").append(n).append("_ms"); }
            h.append(" K_table switch K_all active pending completed");
            System.out.println(h);
            System.out.flush();
            while (true)
            {
                long t0 = System.currentTimeMillis();
                StringBuilder s = new StringBuilder();
                s.append(t0).append(' ').append(pools.get("G1 Eden Space").getUsage().getUsed())
                 .append(' ').append(pools.get("G1 Survivor Space").getUsage().getUsed())
                 .append(' ').append(pools.get("G1 Old Gen").getUsage().getUsed());
                MemoryUsage cu = pools.get("G1 Old Gen").getCollectionUsage();
                s.append(' ').append(cu == null ? -1 : cu.getUsed());
                for (GarbageCollectorMXBean g : gcs) s.append(' ').append(g.getCollectionCount()).append(' ').append(g.getCollectionTime());
                s.append(' ').append(attr(tm + "MemtableOnHeapDataSize", "Value"))
                 .append(' ').append(attr(tm + "MemtableSwitchCount", "Count"))
                 .append(' ').append(attr("org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize", "Value"))
                 .append(' ').append(attr(tp + "ActiveTasks", "Value"))
                 .append(' ').append(attr(tp + "PendingTasks", "Value"))
                 .append(' ').append(attr(tp + "CompletedTasks", "Value"));
                System.out.println(s);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
