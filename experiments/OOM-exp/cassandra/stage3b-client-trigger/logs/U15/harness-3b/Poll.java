// U15 stage-2 poller (from R22's Poll.java; design §2.6). Every <period> ms over JMX: heap pools (Eden/Survivor/Old),
// Old Gen collection usage, GC MXBeans; for table u15.t: MemtableOnHeapDataSize (K_live), AllMemtablesOnHeapDataSize
// (live + flushing, K_all), MemtableSwitchCount, PendingFlushes, WriteLatency count (applied); global AllMemtablesOnHeapDataSize;
// MemtablePool BlockedOnAllocation count and PendingFlushTasks; MutationStage and Native-Transport-Requests
// active/pending/completed; ClientRequest Write Timeouts; DroppedMessage MUTATION_REQ; CommitLog TotalCommitLogSize.
// usage: java Poll <jmx-port> <period-ms>. One line per sample (header first); a missing metric is -1.
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

    // Count for counters/meters/timers, Value for gauges
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
        String t = M + "type=Table,keyspace=u15,scope=t,name=";
        String mut = M + "type=ThreadPools,path=request,scope=MutationStage,name=";
        String ntr = M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=";
        String[][] cols = {
            {"K_live", t + "MemtableOnHeapDataSize"}, {"K_all", t + "AllMemtablesOnHeapDataSize"}, {"sw", t + "MemtableSwitchCount"},
            {"pflush", t + "PendingFlushes"}, {"applied", t + "WriteLatency"},
            {"K_global", M + "type=Table,name=AllMemtablesOnHeapDataSize"},
            {"blocked_alloc", M + "type=MemtablePool,name=BlockedOnAllocation"}, {"pool_pending", M + "type=MemtablePool,name=PendingFlushTasks"},
            {"active", mut + "ActiveTasks"}, {"pending", mut + "PendingTasks"}, {"completed", mut + "CompletedTasks"},
            {"ntr_active", ntr + "ActiveTasks"}, {"ntr_pending", ntr + "PendingTasks"}, {"ntr_completed", ntr + "CompletedTasks"},
            {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped"},
            {"wr_timeouts", M + "type=ClientRequest,scope=Write,name=Timeouts"},
            {"cl_size", M + "type=CommitLog,name=TotalCommitLogSize"},
            {"v_applied", M + "type=Table,keyspace=vks,scope=kv,name=WriteLatency"}, // 3-b confirm: the victim table's applied writes
        };
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            m = c.getMBeanServerConnection();
            for (String[] col : cols) System.err.println(col[0] + " <- " + col[1]);
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
            for (String[] col : cols) h.append(' ').append(col[0]);
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
                for (String[] col : cols) s.append(' ').append(cv(col[1]));
                System.out.println(s);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
