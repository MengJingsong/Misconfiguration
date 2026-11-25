import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.MemoryUsage;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * C2 sampler (adapted from B1Sampler). usage: java C2Sampler <out.csv> <stop-file> [period_ms=1000]
 * One JMX pass per period on 127.0.0.1:7199. Columns:
 *  t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,ntr_completed,rs_active,rs_pending,direct_used,
 *  clients,crs_aborts,young_ms,old_ms,crs_max
 * old_postgc = G1 Old Gen CollectionUsage (occupancy after the last GC that collected the old gen).
 * crs_aborts / crs_max = keyspace c2 CoordinatorReadSizeAborts count / CoordinatorReadSize max (K), -1 if absent.
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
                w.println("t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,ntr_completed,rs_active,rs_pending,direct_used,clients,crs_aborts,young_ms,old_ms,crs_max");
            String ntr = TP + "path=transport,scope=Native-Transport-Requests,name=";
            String rs = TP + "path=request,scope=ReadStage,name=";
            String ks = "org.apache.cassandra.metrics:type=Keyspace,keyspace=c2,name=";
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    w.println(t0 + "," + used(m, "java.lang:type=Memory", "HeapMemoryUsage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "Usage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "CollectionUsage")
                              + "," + num(m, ntr + "ActiveTasks", "Value") + "," + num(m, ntr + "PendingTasks", "Value")
                              + "," + num(m, ntr + "CompletedTasks", "Value")
                              + "," + num(m, rs + "ActiveTasks", "Value") + "," + num(m, rs + "PendingTasks", "Value")
                              + "," + num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed")
                              + "," + num(m, "org.apache.cassandra.metrics:type=Client,name=ConnectedNativeClients", "Value")
                              + "," + num(m, ks + "CoordinatorReadSizeAborts", "Count")
                              + "," + num(m, "java.lang:type=GarbageCollector,name=G1 Young Generation", "CollectionTime")
                              + "," + num(m, "java.lang:type=GarbageCollector,name=G1 Old Generation", "CollectionTime")
                              + "," + num(m, ks + "CoordinatorReadSize", "Max"));
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
