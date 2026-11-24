// R22 stage-2 poller (R17's, keyspace r22) (U11's Poll.java extended per design §2.6): heap pools, Old Gen collection usage, GC MXBeans,
// for both tables r22.rt and r22.blob MemtableOnHeapDataSize / MemtableSwitchCount / WriteLatency count (applied local
// writes), AllMemtablesOnHeapDataSize, MutationStage and Native-Transport-Requests active/pending/completed,
// Storage TotalHintsInProgress / TotalHints, DroppedMessage MUTATION_REQ dropped, ClientRequest Write Timeouts,
// CommitLog TotalCommitLogSize. Every <period> ms over JMX. usage: java Poll <jmx-port> <period-ms>
// One line per sample (space-separated, header first); a metric that does not exist (yet) is -1.
// At start prints to stderr: StorageProxy MaxHintsInProgress and the MBean names used.
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
        String rt = M + "type=Table,keyspace=r22,scope=rt,name=";
        String bl = M + "type=Table,keyspace=r22,scope=blob,name=";
        String mut = M + "type=ThreadPools,path=request,scope=MutationStage,name=";
        String ntr = M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=";
        String[][] cols = {
            {"K_rt", rt + "MemtableOnHeapDataSize"}, {"sw_rt", rt + "MemtableSwitchCount"}, {"wl_rt", rt + "WriteLatency"},
            {"K_blob", bl + "MemtableOnHeapDataSize"}, {"sw_blob", bl + "MemtableSwitchCount"}, {"wl_blob", bl + "WriteLatency"},
            {"K_all", M + "type=Table,name=AllMemtablesOnHeapDataSize"},
            {"active", mut + "ActiveTasks"}, {"pending", mut + "PendingTasks"}, {"completed", mut + "CompletedTasks"},
            {"ntr_active", ntr + "ActiveTasks"}, {"ntr_pending", ntr + "PendingTasks"}, {"ntr_completed", ntr + "CompletedTasks"},
            {"hints_inprog", M + "type=Storage,name=TotalHintsInProgress"}, {"hints_total", M + "type=Storage,name=TotalHints"},
            {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped"},
            {"wr_timeouts", M + "type=ClientRequest,scope=Write,name=Timeouts"},
            {"cl_size", M + "type=CommitLog,name=TotalCommitLogSize"},
        };
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            m = c.getMBeanServerConnection();
            System.err.println("MaxHintsInProgress=" + attr("org.apache.cassandra.db:type=StorageProxy", "MaxHintsInProgress"));
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
