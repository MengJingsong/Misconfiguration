import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness for file_cache_size-chunkcache-weightedsize--autonomous (audit amendment AM5).
 *   java O05Jmx <jmx port>    prints one line "O05JMX t=<epoch ms> key=value ..." with the MBeans of case-file B3d, in bytes.
 * A missing MBean (the ChunkCache metrics do not exist while the cache is disabled) prints "NA".
 */
public class O05Jmx
{
    static final String[][] Q = {
        {"cc_capacity", "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Capacity", "Value"},
        {"cc_size",     "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size", "Value"},
        {"cc_entries",  "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Entries", "Value"},
        {"cc_requests", "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Requests", "Count"},
        {"cc_misses",   "org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Misses", "Count"},
        {"pool_size",   "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size", "Value"},
        {"pool_overflow","org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=OverflowSize", "Value"},
        {"pool_used",   "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize", "Value"},
        {"pool_capacity","org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Capacity", "Value"},
        {"net_size",    "org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size", "Value"},
        {"direct_used", "java.nio:type=BufferPool,name=direct", "MemoryUsed"},
        {"direct_count","java.nio:type=BufferPool,name=direct", "Count"},
        {"direct_cap",  "java.nio:type=BufferPool,name=direct", "TotalCapacity"},
        {"heap_used",   "java.lang:type=Memory", "HeapMemoryUsage"},
    };

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            StringBuilder b = new StringBuilder("O05JMX t=").append(System.currentTimeMillis());
            for (String[] q : Q)
            {
                String v;
                try
                {
                    Object o = m.getAttribute(new ObjectName(q[1]), q[2]);
                    if (o instanceof javax.management.openmbean.CompositeData)
                        o = ((javax.management.openmbean.CompositeData) o).get("used");
                    v = String.valueOf(o);
                }
                catch (javax.management.InstanceNotFoundException e) { v = "NA"; }
                b.append(' ').append(q[0]).append('=').append(v);
            }
            System.out.println(b);
        }
    }
}
