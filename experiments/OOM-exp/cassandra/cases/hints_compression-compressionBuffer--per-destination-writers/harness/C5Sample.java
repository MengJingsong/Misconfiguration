// C5 stage 2 JMX sampler for A (127.0.0.1:7299).
//   java C5Sample loop <intervalMs> <outCsv>     one row per interval until killed (NA rows while A is down)
//   java C5Sample once                           prints "direct_used direct_count direct_cap heap_used total_hints"
// Columns: java.nio BufferPool direct MemoryUsed/Count/TotalCapacity (the JDK Bits counter, the real resource of the
// claimed domain), heap used, Storage TotalHints, HintsService HintsSucceeded/Failed/TimedOut (where present).
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class C5Sample {
    static MBeanServerConnection mbs; static JMXConnector jc;
    static final String URL = "service:jmx:rmi:///jndi/rmi://127.0.0.1:7299/jmxrmi";
    static void connect() {
        try { if (jc != null) jc.close(); } catch (Exception e) {}
        try { jc = JMXConnectorFactory.connect(new JMXServiceURL(URL)); mbs = jc.getMBeanServerConnection(); } catch (Exception e) { jc = null; mbs = null; }
    }
    static long lng(String on, String a) { try { return ((Number) mbs.getAttribute(new ObjectName(on), a)).longValue(); } catch (Exception e) { return -1; } }
    static final String D = "java.nio:type=BufferPool,name=direct", M = "org.apache.cassandra.metrics:";
    static String row() {
        long hu = -1;
        try { hu = ((Number) ((CompositeData) mbs.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")).get("used")).longValue(); } catch (Exception e) {}
        long du = lng(D, "MemoryUsed");
        if (du < 0 && hu < 0) { mbs = null; return null; }
        return du + "," + lng(D, "Count") + "," + lng(D, "TotalCapacity") + "," + hu + "," + lng(M + "type=Storage,name=TotalHints", "Count")
            + "," + lng(M + "type=HintsService,name=HintsSucceeded", "Count") + "," + lng(M + "type=HintsService,name=HintsFailed", "Count")
            + "," + lng(M + "type=HintsService,name=HintsTimedOut", "Count");
    }
    public static void main(String[] a) throws Exception {
        if (a[0].equals("once")) { connect(); String r = mbs == null ? null : row(); System.out.println(r == null ? "NA" : r.replace(',', ' ')); System.exit(0); }
        long iv = Long.parseLong(a[1]);
        PrintWriter csv = new PrintWriter(new FileWriter(a[2], true), true);
        csv.println("epoch_ms,direct_used,direct_count,direct_cap,heap_used,total_hints,hints_succeeded,hints_failed,hints_timedout");
        while (true) {
            long t = System.currentTimeMillis();
            if (mbs == null) connect();
            String r = mbs == null ? null : row();
            csv.println(t + "," + (r == null ? "NA,NA,NA,NA,NA,NA,NA,NA" : r));
            long sl = iv - (System.currentTimeMillis() - t); if (sl > 0) Thread.sleep(sl);
        }
    }
}
