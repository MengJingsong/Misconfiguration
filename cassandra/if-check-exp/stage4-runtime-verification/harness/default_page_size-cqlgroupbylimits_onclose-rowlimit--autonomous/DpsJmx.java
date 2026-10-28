import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness for default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous (amendment C3). Node JMX on 127.0.0.1:<port>, no auth.
 *   java DpsJmx <port> serve                  reads commands on stdin: "alloc" prints "ALLOC <epoch ms> <sum of getThreadAllocatedBytes over all live threads>",
 *                                             "heap" prints "HEAP <epoch ms> <used> <committed>", "quit" exits. One connection for the whole run.
 *   java DpsJmx <port> poll <out> <ms> <stopfile>   appends "<epoch ms>,<heap used>,<committed>" every <ms> ms until <stopfile> exists
 * Derived from ThreadAlloc.java of the tombstone_failure_threshold harness and Jmx.java of the range_tombstone harness.
 */
public class DpsJmx
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            com.sun.management.ThreadMXBean t = ManagementFactory.newPlatformMXBeanProxy(m, ManagementFactory.THREAD_MXBEAN_NAME, com.sun.management.ThreadMXBean.class);
            MemoryMXBean mem = ManagementFactory.newPlatformMXBeanProxy(m, ManagementFactory.MEMORY_MXBEAN_NAME, MemoryMXBean.class);
            if (a[1].equals("serve"))
            {
                BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
                String l;
                while ((l = in.readLine()) != null)
                {
                    if (l.equals("alloc"))
                    {
                        long[] ids = t.getAllThreadIds();
                        long[] al = t.getThreadAllocatedBytes(ids);
                        long tot = 0;
                        for (long x : al) if (x > 0) tot += x;
                        System.out.println("ALLOC " + System.currentTimeMillis() + " " + tot);
                    }
                    else if (l.equals("heap"))
                    {
                        java.lang.management.MemoryUsage mu = mem.getHeapMemoryUsage();
                        System.out.println("HEAP " + System.currentTimeMillis() + " " + mu.getUsed() + " " + mu.getCommitted());
                    }
                    else if (l.equals("quit")) break;
                    System.out.flush();
                }
            }
            else if (a[1].equals("poll"))
            {
                long ms = Long.parseLong(a[3]);
                File stop = new File(a[4]);
                try (FileWriter w = new FileWriter(a[2], true))
                {
                    while (!stop.exists())
                    {
                        long t0 = System.currentTimeMillis();
                        java.lang.management.MemoryUsage mu = mem.getHeapMemoryUsage();
                        w.write(t0 + "," + mu.getUsed() + "," + mu.getCommitted() + "\n");
                        w.flush();
                        long d = ms - (System.currentTimeMillis() - t0);
                        if (d > 0) Thread.sleep(d);
                    }
                }
            }
        }
    }
}
