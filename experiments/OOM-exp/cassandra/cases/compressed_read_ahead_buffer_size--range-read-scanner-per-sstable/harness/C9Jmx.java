import java.io.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * C9 stage-2 JMX helper (design §2.5 step 3, §2.6).
 *   java C9Jmx poll <port> <out.csv> <interval-ms>   sampler; failed reads are -1; reconnects; exits after 30 consecutive failures
 *   java C9Jmx flushsrv <port>                        reads lines from stdin; "flush" -> StorageService.forceKeyspaceFlush("c9","t"),
 *                                                     prints "ok <LiveSSTableCount>"; "count" prints the count; "quit" exits
 *   java C9Jmx count <port>                           prints LiveSSTableCount of c9.t and pending compactions
 */
public class C9Jmx
{
    static final String M = "org.apache.cassandra.metrics:";

    static long attr(MBeanServerConnection m, String on, String... attrs)
    {
        for (String a : attrs)
        {
            try
            {
                return ((Number) m.getAttribute(new ObjectName(on), a)).longValue();
            }
            catch (Exception e) { }
        }
        return -1;
    }

    static MBeanServerConnection connect(int port) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        JMXConnector c = JMXConnectorFactory.connect(u);
        return c.getMBeanServerConnection();
    }

    static long live(MBeanServerConnection m)
    {
        return attr(m, M + "type=Table,keyspace=c9,scope=t,name=LiveSSTableCount", "Value");
    }

    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[1]);
        if (a[0].equals("count"))
        {
            MBeanServerConnection m = connect(port);
            System.out.println("live " + live(m) + " pending_compactions " + attr(m, M + "type=Compaction,name=PendingTasks", "Value")
                               + " table_pending " + attr(m, M + "type=Table,keyspace=c9,scope=t,name=PendingCompactions", "Value"));
            System.exit(0);
        }
        if (a[0].equals("flushsrv"))
        {
            MBeanServerConnection m = connect(port);
            ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
            BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
            String l;
            while ((l = r.readLine()) != null)
            {
                l = l.trim();
                if (l.equals("quit")) break;
                try
                {
                    if (l.equals("flush"))
                        m.invoke(ss, "forceKeyspaceFlush", new Object[]{ "c9", new String[]{ "t" } },
                                 new String[]{ "java.lang.String", "[Ljava.lang.String;" });
                    System.out.println("ok " + live(m));
                }
                catch (Exception e)
                {
                    System.out.println("err " + e);
                }
                System.out.flush();
            }
            System.exit(0);
        }
        // poll
        long interval = Long.parseLong(a[3]);
        PrintWriter w = new PrintWriter(new FileWriter(a[2], true), true);
        w.println("ms,direct_count,direct_used,direct_cap,mapped_count,cc_size,cc_used,cc_overflow,net_size,net_used,net_overflow,"
                  + "read_active,read_pending,read_completed,live_sstables,heap_used,heap_committed,young_gc,old_gc,young_gc_ms,old_gc_ms");
        int fails = 0;
        while (fails < 30)
        {
            try
            {
                MBeanServerConnection m = connect(port);
                fails = 0;
                while (true)
                {
                    long t = System.currentTimeMillis();
                    String d = "java.nio:type=BufferPool,name=direct";
                    String mp = "java.nio:type=BufferPool,name=mapped";
                    String cc = M + "type=BufferPool,scope=chunk-cache,name=";
                    String nt = M + "type=BufferPool,scope=networking,name=";
                    String rs = M + "type=ThreadPools,path=request,scope=ReadStage,name=";
                    CompositeData h = (CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage");
                    String yg = "java.lang:type=GarbageCollector,name=G1 Young Generation";
                    String og = "java.lang:type=GarbageCollector,name=G1 Old Generation";
                    w.println(t + "," + attr(m, d, "Count") + "," + attr(m, d, "MemoryUsed") + "," + attr(m, d, "TotalCapacity") + ","
                              + attr(m, mp, "Count") + ","
                              + attr(m, cc + "Size", "Value") + "," + attr(m, cc + "UsedSize", "Value") + "," + attr(m, cc + "OverflowSize", "Value") + ","
                              + attr(m, nt + "Size", "Value") + "," + attr(m, nt + "UsedSize", "Value") + "," + attr(m, nt + "OverflowSize", "Value") + ","
                              + attr(m, rs + "ActiveTasks", "Value") + "," + attr(m, rs + "PendingTasks", "Value") + "," + attr(m, rs + "CompletedTasks", "Value") + ","
                              + live(m) + "," + h.get("used") + "," + h.get("committed") + ","
                              + attr(m, yg, "CollectionCount") + "," + attr(m, og, "CollectionCount") + ","
                              + attr(m, yg, "CollectionTime") + "," + attr(m, og, "CollectionTime"));
                    long s = interval - (System.currentTimeMillis() - t);
                    if (s > 0) Thread.sleep(s);
                }
            }
            catch (Exception e)
            {
                fails++;
                Thread.sleep(1000);
            }
        }
    }
}
