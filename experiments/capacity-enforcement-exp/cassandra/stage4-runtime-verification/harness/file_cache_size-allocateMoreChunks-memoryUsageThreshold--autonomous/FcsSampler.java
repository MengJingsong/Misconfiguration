import java.io.File;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * JMX sampler (C3 as amended 2026-10-27) for file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.
 * Replaces B3d's "nodetool sjk mx" calls (one JVM per call, exit 0 on failure on this host). Connection code follows
 * harness/column_index_cache_size-indexSamples-cacheSizeThreshold--guided/Jmx.java (that file is not modified).
 *
 * usage: java FcsSampler <periodMs> <stopFile>    (node JMX on 127.0.0.1:7199, no auth)
 * Prints one line per period until <stopFile> exists:
 *   FCSS <epochMs> cc_size=<> cc_overflow=<> cc_size2=<> cc_used=<> cc_capacity=<> nw_size=<> nw_overflow=<> nw_used=<> nw_capacity=<>
 *        direct_used=<> direct_count=<> direct_capacity=<>
 * cc_size2 is a second read of chunk-cache Size after cc_overflow, so a reader can see whether the pair moved in between.
 */
public class FcsSampler
{
    static final String BP = "org.apache.cassandra.metrics:type=BufferPool,scope=%s,name=%s";

    static Object g(MBeanServerConnection m, String scope, String name) throws Exception
    {
        return m.getAttribute(new ObjectName(String.format(BP, scope, name)), "Value");
    }

    public static void main(String[] a) throws Exception
    {
        long period = Long.parseLong(a[0]);
        File stop = new File(a[1]);
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
            while (!stop.exists())
            {
                long t0 = System.currentTimeMillis();
                StringBuilder sb = new StringBuilder("FCSS ").append(t0);
                sb.append(" cc_size=").append(g(m, "chunk-cache", "Size"));
                sb.append(" cc_overflow=").append(g(m, "chunk-cache", "OverflowSize"));
                sb.append(" cc_size2=").append(g(m, "chunk-cache", "Size"));
                sb.append(" cc_used=").append(g(m, "chunk-cache", "UsedSize"));
                sb.append(" cc_capacity=").append(g(m, "chunk-cache", "Capacity"));
                sb.append(" nw_size=").append(g(m, "networking", "Size"));
                sb.append(" nw_overflow=").append(g(m, "networking", "OverflowSize"));
                sb.append(" nw_used=").append(g(m, "networking", "UsedSize"));
                sb.append(" nw_capacity=").append(g(m, "networking", "Capacity"));
                sb.append(" direct_used=").append(m.getAttribute(direct, "MemoryUsed"));
                sb.append(" direct_count=").append(m.getAttribute(direct, "Count"));
                sb.append(" direct_capacity=").append(m.getAttribute(direct, "TotalCapacity"));
                System.out.println(sb);
                System.out.flush();
                long sl = period - (System.currentTimeMillis() - t0);
                if (sl > 0)
                    Thread.sleep(sl);
            }
        }
    }
}
