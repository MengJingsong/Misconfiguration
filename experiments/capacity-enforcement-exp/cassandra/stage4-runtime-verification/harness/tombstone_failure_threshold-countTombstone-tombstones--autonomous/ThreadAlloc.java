// Stage-4 harness (tombstone_failure_threshold, audit amendment R5): node-wide allocated bytes over JMX.
// usage: java ThreadAlloc <jmx-port>   prints: epoch_ms total=<sum of getThreadAllocatedBytes over all live threads>
//        threads=<n> read=<sum over threads named ReadStage*> ntr=<sum over Native-Transport-Requests*>
// (SEP worker threads are renamed per task, so read/ntr are indicative only; total is the reading.)
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class ThreadAlloc
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            com.sun.management.ThreadMXBean t = ManagementFactory.newPlatformMXBeanProxy(m, ManagementFactory.THREAD_MXBEAN_NAME, com.sun.management.ThreadMXBean.class);
            long[] ids = t.getAllThreadIds();
            long[] al = t.getThreadAllocatedBytes(ids);
            java.lang.management.ThreadInfo[] inf = t.getThreadInfo(ids);
            long tot = 0, rd = 0, ntr = 0; int n = 0;
            for (int i = 0; i < ids.length; i++)
            {
                if (al[i] < 0 || inf[i] == null) continue;
                tot += al[i]; n++;
                String nm = inf[i].getThreadName();
                if (nm.startsWith("ReadStage")) rd += al[i];
                if (nm.startsWith("Native-Transport-Requests")) ntr += al[i];
            }
            System.out.println(System.currentTimeMillis() + " total=" + tot + " threads=" + n + " read=" + rd + " ntr=" + ntr);
        }
    }
}
