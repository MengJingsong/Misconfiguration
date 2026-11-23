// U12 sampler (O1; adapted from R7's U1R2Sample, JMX part only). Runs on the node host, JMX on 127.0.0.1:<port>.
//   java U12Sample <jmxPort> <intervalMs> <outDir>
// U_direct = java.nio BufferPool "direct" MemoryUsed / TotalCapacity / Count (JDK Bits counter, independent of any
// Cassandra counter); heap used; Compaction BytesCompacted, PendingTasks, CompletedTasks; networking BufferPool size.
// Keeps writing NA when the node is down so the time of death shows.
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class U12Sample {
    static MBeanServerConnection mbs; static JMXConnector jc; static String url;
    static Object attr(String on, String a) { try { return mbs.getAttribute(new ObjectName(on), a); } catch (Exception e) { return null; } }
    static long lng(Object o) { return o == null ? -1 : ((Number) o).longValue(); }
    static void connect() {
        try { if (jc != null) jc.close(); } catch (Exception e) {}
        try { jc = JMXConnectorFactory.connect(new JMXServiceURL(url)); mbs = jc.getMBeanServerConnection(); } catch (Exception e) { jc = null; mbs = null; }
    }
    static final String M = "org.apache.cassandra.metrics:";
    static final String[][] COLS = {
        {"direct_used", "java.nio:type=BufferPool,name=direct", "MemoryUsed"},
        {"direct_capacity", "java.nio:type=BufferPool,name=direct", "TotalCapacity"},
        {"direct_count", "java.nio:type=BufferPool,name=direct", "Count"},
        {"cmp_bytes", M + "type=Compaction,name=BytesCompacted", "Count"},
        {"cmp_pending", M + "type=Compaction,name=PendingTasks", "Value"},
        {"cmp_completed", M + "type=Compaction,name=CompletedTasks", "Value"},
        {"net_pool_size", M + "type=BufferPool,scope=networking,name=Size", "Value"},
        {"live_sstables", M + "type=Table,keyspace=u12,scope=t,name=LiveSSTableCount", "Value"},
    };
    public static void main(String[] a) throws Exception {
        url = "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi";
        long iv = Long.parseLong(a[1]); File out = new File(a[2]);
        PrintWriter csv = new PrintWriter(new FileWriter(new File(out, "samples.csv"), true), true);
        StringBuilder h = new StringBuilder("epoch_ms,heap_used");
        for (String[] c : COLS) h.append(',').append(c[0]);
        csv.println(h);
        while (true) {
            long t = System.currentTimeMillis();
            if (mbs == null) connect();
            StringBuilder sb = new StringBuilder().append(t);
            if (mbs != null) {
                Object hm = attr("java.lang:type=Memory", "HeapMemoryUsage");
                long hu = hm == null ? -1 : lng(((CompositeData) hm).get("used"));
                long du = lng(attr(COLS[0][1], COLS[0][2]));
                if (du < 0 && hu < 0) { mbs = null; sb.append(",NA"); for (String[] c : COLS) sb.append(",NA"); }
                else { sb.append(',').append(hu); for (String[] c : COLS) sb.append(',').append(lng(attr(c[1], c[2]))); }
            } else { sb.append(",NA"); for (String[] c : COLS) sb.append(",NA"); }
            csv.println(sb);
            long sl = iv - (System.currentTimeMillis() - t);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
