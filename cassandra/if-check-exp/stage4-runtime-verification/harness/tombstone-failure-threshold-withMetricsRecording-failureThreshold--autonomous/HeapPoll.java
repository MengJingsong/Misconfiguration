// Stage-4 harness (tombstone_failure_threshold, runbook fix D3): jstat's EU/OU over JMX, because the shipped
// jvm11-server.options sets -XX:+PerfDisableSharedMem and jstat cannot attach.
// usage: java HeapPoll <jmx-port> <period-ms> <count, 0 = until killed>
// prints a header, then per sample: epoch_ms EU OU SU (bytes used of the G1 Eden Space, G1 Old Gen, G1 Survivor Space)
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.util.*;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.*;

public class HeapPoll
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        long period = Long.parseLong(a[1]); long count = Long.parseLong(a[2]);
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            Map<String, MemoryPoolMXBean> pools = new HashMap<>();
            for (ObjectName on : m.queryNames(new ObjectName(ManagementFactory.MEMORY_POOL_MXBEAN_DOMAIN_TYPE + ",*"), null))
            {
                MemoryPoolMXBean p = ManagementFactory.newPlatformMXBeanProxy(m, on.toString(), MemoryPoolMXBean.class);
                pools.put(p.getName(), p);
            }
            System.out.println("epoch_ms EU OU SU");
            for (long i = 0; count == 0 || i < count; i++)
            {
                long t0 = System.currentTimeMillis();
                System.out.println(t0 + " " + pools.get("G1 Eden Space").getUsage().getUsed() + " " + pools.get("G1 Old Gen").getUsage().getUsed()
                                   + " " + pools.get("G1 Survivor Space").getUsage().getUsed());
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
