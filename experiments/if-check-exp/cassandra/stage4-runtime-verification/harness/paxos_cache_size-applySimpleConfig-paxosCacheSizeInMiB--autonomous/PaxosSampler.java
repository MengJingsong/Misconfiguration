import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.
 * The one-connection pattern of harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/CounterCacheSampler.java
 * (jstat cannot attach here); no metric exposes PaxosState.RECENT, so this samples the traffic and the heap only. Every 2 s appends
 *   epoch_ms,phase,heap_used,heap_committed,cas_write,cas_prepare,cas_propose,cas_commit
 * (java.lang:type=Memory HeapMemoryUsage; org.apache.cassandra.metrics:type=ClientRequest,scope=CASWrite,name=Latency Count;
 * org.apache.cassandra.metrics:type=Table,keyspace=<ks>,scope=<t>,name=CasPrepareLatency|CasProposeLatency|CasCommitLatency Count,
 * TableMetrics.java:807-809) to <csv>, each value NA while it cannot be read, with the phase label from <phasefile>, until <stopfile>
 * exists.   usage: java PaxosSampler <port> <csv> <phasefile> <stopfile> <keyspace> <table>
 */
public class PaxosSampler
{
    static String get(MBeanServerConnection m, ObjectName n, String a)
    {
        try
        {
            Object v = m.getAttribute(n, a);
            return String.valueOf(v);
        }
        catch (Exception e)
        {
            return "NA";
        }
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        String t = "org.apache.cassandra.metrics:type=Table,keyspace=" + a[4] + ",scope=" + a[5] + ",name=";
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        ObjectName cw = new ObjectName("org.apache.cassandra.metrics:type=ClientRequest,scope=CASWrite,name=Latency");
        ObjectName pr = new ObjectName(t + "CasPrepareLatency"), po = new ObjectName(t + "CasProposeLatency"), co = new ObjectName(t + "CasCommitLatency");
        File phase = new File(a[2]), stop = new File(a[3]);
        try (JMXConnector c = JMXConnectorFactory.connect(u);
             PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            w.println("epoch_ms,phase,heap_used,heap_committed,cas_write,cas_prepare,cas_propose,cas_commit");
            long next = System.currentTimeMillis();
            while (true)
            {
                boolean last = stop.exists();
                long now = System.currentTimeMillis();
                String ph = phase.exists() ? new String(Files.readAllBytes(phase.toPath())).trim() : "";
                String hu = "NA", hc = "NA";
                try
                {
                    CompositeData h = (CompositeData) m.getAttribute(mem, "HeapMemoryUsage");
                    hu = String.valueOf(h.get("used"));
                    hc = String.valueOf(h.get("committed"));
                }
                catch (Exception e)
                {
                    // leave NA
                }
                w.println(now + "," + ph + "," + hu + "," + hc + "," + get(m, cw, "Count") + "," + get(m, pr, "Count") + ","
                          + get(m, po, "Count") + "," + get(m, co, "Count"));
                if (last) break;
                next += 2000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
