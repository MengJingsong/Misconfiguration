import java.io.File;
import java.io.FileWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier (B3d, amendment AM4) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
 * One long-lived JMX client on 127.0.0.1:<port>, no auth.
 *   java CcJmx.java <port> poll <out.csv> <ms> <stopfile>   appends one CSV row every <ms> ms until <stopfile> exists
 *   java CcJmx.java <port> once <out.csv>                   appends one row
 * A gauge whose MBean does not exist (chunk cache disabled) is written as an empty field.
 */
public class CcJmx
{
    static final String M = "org.apache.cassandra.metrics:";
    static final String[][] COLS = {
        {"cc_capacity", M + "type=Cache,scope=ChunkCache,name=Capacity", "Value"},
        {"cc_size", M + "type=Cache,scope=ChunkCache,name=Size", "Value"},
        {"cc_entries", M + "type=Cache,scope=ChunkCache,name=Entries", "Value"},
        {"cc_misses", M + "type=Cache,scope=ChunkCache,name=Misses", "Count"},
        {"cc_hits", M + "type=Cache,scope=ChunkCache,name=Hits", "Count"},
        {"ccpool_size", M + "type=BufferPool,scope=chunk-cache,name=Size", "Value"},
        {"ccpool_used", M + "type=BufferPool,scope=chunk-cache,name=UsedSize", "Value"},
        {"ccpool_overflow", M + "type=BufferPool,scope=chunk-cache,name=OverflowSize", "Value"},
        {"ccpool_capacity", M + "type=BufferPool,scope=chunk-cache,name=Capacity", "Value"},
        {"netpool_size", M + "type=BufferPool,scope=networking,name=Size", "Value"},
        {"netpool_overflow", M + "type=BufferPool,scope=networking,name=OverflowSize", "Value"},
        {"direct_used", "java.nio:type=BufferPool,name=direct", "MemoryUsed"},
        {"direct_capacity", "java.nio:type=BufferPool,name=direct", "TotalCapacity"},
        {"direct_count", "java.nio:type=BufferPool,name=direct", "Count"},
        {"heap_used", "java.lang:type=Memory", "HeapMemoryUsage"},
    };

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            File out = new File(a[2]);
            boolean header = !out.exists() || out.length() == 0;
            try (FileWriter w = new FileWriter(out, true))
            {
                if (header)
                {
                    StringBuilder h = new StringBuilder("epoch_ms");
                    for (String[] col : COLS) h.append(',').append(col[0]);
                    w.write(h.append('\n').toString());
                    w.flush();
                }
                if (a[1].equals("once")) { w.write(row(m)); return; }
                long ms = Long.parseLong(a[3]);
                File stop = new File(a[4]);
                while (!stop.exists())
                {
                    long t0 = System.currentTimeMillis();
                    w.write(row(m));
                    w.flush();
                    long sl = ms - (System.currentTimeMillis() - t0);
                    if (sl > 0) Thread.sleep(sl);
                }
            }
        }
    }

    static String row(MBeanServerConnection m)
    {
        StringBuilder b = new StringBuilder(Long.toString(System.currentTimeMillis()));
        for (String[] col : COLS)
        {
            b.append(',');
            try
            {
                Object v = m.getAttribute(new ObjectName(col[1]), col[2]);
                if (v instanceof javax.management.openmbean.CompositeData) v = ((javax.management.openmbean.CompositeData) v).get("used");
                b.append(v);
            }
            catch (Exception e) { /* absent MBean: empty field */ }
        }
        return b.append('\n').toString();
    }
}
