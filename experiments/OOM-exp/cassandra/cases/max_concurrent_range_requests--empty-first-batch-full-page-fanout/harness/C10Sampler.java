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
 * C10 sampler (C2Sampler with the range-request metrics). usage: java C10Sampler <out.csv> <stop-file> [period_ms=1000] [jmxPort=7199]
 * Columns: t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,ntr_completed,rs_active,rs_pending,direct_used,
 *  clients,young_ms,old_ms,rt_count,rt_mean,rt_max,rng_timeouts,rng_failures,rng_latency_count
 * old_postgc = G1 Old Gen CollectionUsage. rt_* = ClientRequest RangeSlice RoundTripsPerReadHistogram (count, mean, max).
 */
public class C10Sampler
{
    static final String TP = "org.apache.cassandra.metrics:type=ThreadPools,";

    static double num(MBeanServerConnection m, String bean, String attr)
    {
        try { return ((Number) m.getAttribute(new ObjectName(bean), attr)).doubleValue(); }
        catch (Exception e) { return -1; }
    }

    static long used(MBeanServerConnection m, String bean, String attr)
    {
        try { return MemoryUsage.from((CompositeData) m.getAttribute(new ObjectName(bean), attr)).getUsed(); }
        catch (Exception e) { return -1; }
    }

    static String l(double d) { return Long.toString((long) d); }

    public static void main(String[] a) throws Exception
    {
        String out = a[0];
        File stop = new File(a[1]);
        long period = a.length > 2 ? Long.parseLong(a[2]) : 1000;
        int port = a.length > 3 ? Integer.parseInt(a[3]) : 7199;
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        boolean header = !new File(out).exists();
        try (JMXConnector c = JMXConnectorFactory.connect(u); PrintWriter w = new PrintWriter(new FileWriter(out, true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (header)
                w.println("t_ms,heap_used,old_used,old_postgc,ntr_active,ntr_pending,ntr_completed,rs_active,rs_pending,direct_used,clients,young_ms,old_ms,rt_count,rt_mean,rt_max,rng_timeouts,rng_failures,rng_latency_count");
            String ntr = TP + "path=transport,scope=Native-Transport-Requests,name=";
            String rs = TP + "path=request,scope=ReadStage,name=";
            String rr = "org.apache.cassandra.metrics:type=ClientRequest,scope=RangeSlice,name=";
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                try
                {
                    w.println(t0 + "," + used(m, "java.lang:type=Memory", "HeapMemoryUsage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "Usage")
                              + "," + used(m, "java.lang:type=MemoryPool,name=G1 Old Gen", "CollectionUsage")
                              + "," + l(num(m, ntr + "ActiveTasks", "Value")) + "," + l(num(m, ntr + "PendingTasks", "Value"))
                              + "," + l(num(m, ntr + "CompletedTasks", "Value"))
                              + "," + l(num(m, rs + "ActiveTasks", "Value")) + "," + l(num(m, rs + "PendingTasks", "Value"))
                              + "," + l(num(m, "java.nio:type=BufferPool,name=direct", "MemoryUsed"))
                              + "," + l(num(m, "org.apache.cassandra.metrics:type=Client,name=ConnectedNativeClients", "Value"))
                              + "," + l(num(m, "java.lang:type=GarbageCollector,name=G1 Young Generation", "CollectionTime"))
                              + "," + l(num(m, "java.lang:type=GarbageCollector,name=G1 Old Generation", "CollectionTime"))
                              + "," + l(num(m, rr + "RoundTripsPerReadHistogram", "Count"))
                              + "," + String.format("%.3f", num(m, rr + "RoundTripsPerReadHistogram", "Mean"))
                              + "," + l(num(m, rr + "RoundTripsPerReadHistogram", "Max"))
                              + "," + l(num(m, rr + "Timeouts", "Count"))
                              + "," + l(num(m, rr + "Failures", "Count"))
                              + "," + l(num(m, rr + "Latency", "Count")));
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
