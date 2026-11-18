// C7 victim sampler (adapted from R7's U1R2Sample: CQL part and mutation columns dropped). Runs on ms0625 against n1.
// JMX, 1 s: U_direct = java.nio direct MemoryUsed / Count (JDK Bits counter, read by no repair code), heap used,
// networking BufferPool size / overflow, ValidationExecutor active/pending/completed, AntiEntropyStage active/pending/completed.
//   java C7Sample <jmxPort> <intervalMs> <outDir>
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class C7Sample {
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
        {"direct_count", "java.nio:type=BufferPool,name=direct", "Count"},
        {"net_pool_size", M + "type=BufferPool,scope=networking,name=Size", "Value"},
        {"net_pool_overflow", M + "type=BufferPool,scope=networking,name=OverflowSize", "Value"},
        {"val_active", M + "type=ThreadPools,path=internal,scope=ValidationExecutor,name=ActiveTasks", "Value"},
        {"val_pending", M + "type=ThreadPools,path=internal,scope=ValidationExecutor,name=PendingTasks", "Value"},
        {"val_completed", M + "type=ThreadPools,path=internal,scope=ValidationExecutor,name=CompletedTasks", "Value"},
        {"ae_active", M + "type=ThreadPools,path=internal,scope=AntiEntropyStage,name=ActiveTasks", "Value"},
        {"ae_pending", M + "type=ThreadPools,path=internal,scope=AntiEntropyStage,name=PendingTasks", "Value"},
        {"ae_completed", M + "type=ThreadPools,path=internal,scope=AntiEntropyStage,name=CompletedTasks", "Value"},
    };
    public static void main(String[] a) throws Exception {
        if (a[0].equals("get")) {   // java C7Sample get <jmxPort> <objectName> <attr> ... : read-back of resolved settings
            url = "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[1] + "/jmxrmi"; connect();
            for (int i = 3; i < a.length; i++) System.out.println(a[i] + "=" + attr(a[2], a[i]));
            System.exit(0);
        }
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
                if (du < 0 && hu < 0) { mbs = null; }
                sb.append(',').append(hu);
                for (String[] c : COLS) sb.append(',').append(lng(attr(c[1], c[2])));
            } else { sb.append(",NA"); for (String[] c : COLS) sb.append(",NA"); }
            csv.println(sb);
            long sl = iv - (System.currentTimeMillis() - t);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
