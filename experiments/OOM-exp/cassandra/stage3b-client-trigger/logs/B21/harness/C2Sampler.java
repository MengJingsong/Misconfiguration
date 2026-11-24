import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.MemoryUsage;
import java.util.Set;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * B21 sampler (adapted from B17's C2Sampler). usage: java C2Sampler <out.csv> <stop-file> [period_ms=1000]
 * One JMX pass per period on 127.0.0.1:7199. Columns:
 *  t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,rs_active,rs_pending,rs_completed,direct_used,
 *  lm_pending_bytes,lm_completed_bytes,lm_drop_overload,lm_drop_overload_bytes,lm_drop_timeout,lm_drop_error,young_ms,old_ms
 * old_postgc = G1 Old Gen CollectionUsage (occupancy after the last GC that collected the old gen).
 * lm_* = sum over every org.apache.cassandra.metrics:type=Connection,scope=* (one scope: the self endpoint on one node)
 * of LargeMessagePendingBytes, LargeMessageCompletedBytes, LargeMessageDroppedTasksDueToOverload,
 * LargeMessageDroppedBytesDueToOverload, LargeMessageDroppedTasksDueToTimeout, LargeMessageDroppedTasksDueToError.
 */
public class C2Sampler
{
    static final String TP = "org.apache.cassandra.metrics:type=ThreadPools,";

    static long num(MBeanServerConnection m, String bean, String attr)
    {
        try { return ((Number) m.getAttribute(new ObjectName(bean), attr)).longValue(); }
        catch (Exception e) { return -1; }
    }

    static long used(MBeanServerConnection m, String bean, String attr)
    {
        try { return MemoryUsage.from((CompositeData) m.getAttribute(new ObjectName(bean), attr)).getUsed(); }
        catch (Exception e) { return -1; }
    }

    static long conn(MBeanServerConnection m, String name)
    {
        try
        {
            Set<ObjectName> ns = m.queryNames(new ObjectName("org.apache.cassandra.metrics:type=Connection,name=" + name + ",*"), null);
            if (ns.isEmpty()) return -1;
            long s = 0;
            for (ObjectName n : ns) s += ((Number) m.getAttribute(n, "Value")).longValue();
            return s;
        }
        catch (Exception e) { return -1; }
    }

    public static void main(String[] a) throws Exception
    {
        String out = a[0];
        File stop = new File(a[1]);
        long period = a.length > 2 ? Long.parseLong(a[2]) : 1000;
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        boolean header = !new File(out).exists();
        try (JMXConnector c = JMXConnectorFactory.connect(u); PrintWriter w = new PrintWriter(new FileWriter(out, true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (header)
                w.println("t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,rs_active,rs_pending,rs_completed,direct_used,"
                          + "lm_pending_bytes,lm_completed_bytes,lm_drop_overload,lm_drop_overload_bytes,lm_drop_timeout,lm_drop_error,young_ms,old_ms");
            String ntr = TP + "path=transport,scope=Native-Transport-Requests,name=";
            String rs = TP + "path=request,scope=ReadStage,name=";
            boolean scopes = false;
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    if (!scopes)
                    {
                        Set<ObjectName> ns = m.queryNames(new ObjectName("org.apache.cassandra.metrics:type=Connection,name=LargeMessageCompletedBytes,*"), null);
                        if (!ns.isEmpty()) { System.out.println("connection scopes: " + ns); scopes = true; }
                    }
                    w.println(t0 + "," + used(m, "java.lang:type=Memory", "HeapMemoryUsage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "Usage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "CollectionUsage")
                              + "," + num(m, ntr + "ActiveTasks", "Value") + "," + num(m, ntr + "PendingTasks", "Value")
                              + "," + num(m, rs + "ActiveTasks", "Value") + "," + num(m, rs + "PendingTasks", "Value")
                              + "," + num(m, rs + "CompletedTasks", "Value")
                              + "," + num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed")
                              + "," + conn(m, "LargeMessagePendingBytes") + "," + conn(m, "LargeMessageCompletedBytes")
                              + "," + conn(m, "LargeMessageDroppedTasksDueToOverload") + "," + conn(m, "LargeMessageDroppedBytesDueToOverload")
                              + "," + conn(m, "LargeMessageDroppedTasksDueToTimeout") + "," + conn(m, "LargeMessageDroppedTasksDueToError")
                              + "," + num(m, "java.lang:type=GarbageCollector,name=G1 Young Generation", "CollectionTime")
                              + "," + num(m, "java.lang:type=GarbageCollector,name=G1 Old Generation", "CollectionTime"));
                }
                catch (Exception e)
                {
                    w.println(t0 + ",ERR " + e);
                    if (e instanceof java.io.IOException) return;
                }
                long d = period - (System.currentTimeMillis() - t0);
                if (d > 0) Thread.sleep(d);
            }
        }
    }
}
