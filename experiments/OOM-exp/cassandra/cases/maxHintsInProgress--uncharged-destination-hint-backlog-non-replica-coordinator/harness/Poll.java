// B23 stage-2 JMX poller (from R22's Poll.java). usage: java Poll <jmx-port> <period-ms>
// One line per sample, header first; a metric that does not exist (yet) is -1.
// Columns: heap pools (eden, survivor, old, old after last collection), GC MXBean counts/times, direct BufferPool used,
// MutationStage active/pending/completed, Native-Transport-Requests active/pending/completed,
// Storage TotalHintsInProgress (K) / TotalHints, ClientRequest Write Unavailables / Timeouts / Failures / Latency count
// (completed coordinator writes), DroppedMessage MUTATION_REQ / HINT_REQ dropped.
// At start prints to stderr: StorageProxy MaxHintsInProgress (the contract value C in tasks).
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
        String mut = M + "type=ThreadPools,path=request,scope=MutationStage,name=";
        String ntr = M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=";
        String cw = M + "type=ClientRequest,scope=Write,name=";
        String[][] cols = {
            {"mut_active", mut + "ActiveTasks"}, {"mut_pending", mut + "PendingTasks"}, {"mut_completed", mut + "CompletedTasks"},
            {"ntr_active", ntr + "ActiveTasks"}, {"ntr_pending", ntr + "PendingTasks"}, {"ntr_completed", ntr + "CompletedTasks"},
            {"K", M + "type=Storage,name=TotalHintsInProgress"}, {"hints_total", M + "type=Storage,name=TotalHints"},
            {"unavail", cw + "Unavailables"}, {"timeouts", cw + "Timeouts"}, {"failures", cw + "Failures"}, {"wr_done", cw + "Latency"},
            {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped"},
            {"dropped_hint", M + "type=DroppedMessage,scope=HINT_REQ,name=Dropped"},
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
            h.append(" direct");
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
                s.append(' ').append(attr("java.nio:type=BufferPool,name=direct", "MemoryUsed"));
                for (String[] col : cols) s.append(' ').append(cv(col[1]));
                System.out.println(s);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
