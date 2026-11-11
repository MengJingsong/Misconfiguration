/* Stage-4 sampler for nativecell-int-max-size-NativeCell-size--autonomous. Not upstream code.
 * Usage: java -cp <dir> JmxSampler <jmxPort> <nodePid> <outCsv> <periodMs>
 * Every period: epoch_ms, RssAnon (kB) of the node PID, AllMemtablesOffHeapSize and MemtableOffHeapSize of ks.t, CommitLog OverSizedMutations Count.
 * A value that cannot be read (MBean not yet registered) is written as -1. Stops when killed. */
import java.io.*;
import javax.management.*;
import javax.management.remote.*;

public class JmxSampler
{
    static long rssAnonKb(String pid) throws IOException
    {
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/" + pid + "/status")))
        {
            String l;
            while ((l = r.readLine()) != null)
                if (l.startsWith("RssAnon:")) return Long.parseLong(l.replaceAll("[^0-9]", ""));
        }
        return -1;
    }

    static long get(MBeanServerConnection c, String name, String attr)
    {
        try { ObjectName on = new ObjectName(name); if (!c.isRegistered(on)) return -1; return ((Number) c.getAttribute(on, attr)).longValue(); }
        catch (Exception e) { return -1; }
    }

    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]); String pid = a[1]; long period = Long.parseLong(a[3]);
        JMXConnector jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi"));
        MBeanServerConnection c = jc.getMBeanServerConnection();
        String t = "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=";
        try (PrintWriter w = new PrintWriter(new FileWriter(a[2]), false))
        {
            w.println("epoch_ms,rss_anon_kb,all_memtables_offheap,memtable_offheap,oversized_mutations");
            while (true)
            {
                long now = System.currentTimeMillis();
                w.println(now + "," + rssAnonKb(pid) + "," + get(c, t + "AllMemtablesOffHeapSize", "Value") + "," + get(c, t + "MemtableOffHeapSize", "Value")
                          + "," + get(c, "org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations", "Count"));
                w.flush();
                long left = period - (System.currentTimeMillis() - now);
                if (left > 0) Thread.sleep(left);
            }
        }
    }
}
