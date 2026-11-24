// B19 victim sampler (derived from B9Sample, JMX only). One line per tick into <outDir>/samples.csv.
// K = Client.RequestsSize (global in-flight bytes; one client IP here, so = the per-IP usage).
//   java B19Sample.java <jmxPort> <intervalMs> <outDir>
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class B19Sample {
    static MBeanServerConnection mbs; static JMXConnector jc; static String url;
    static Object attr(String on, String a) { try { return mbs.getAttribute(new ObjectName(on), a); } catch (Exception e) { return null; } }
    static long lng(Object o) { return o == null ? -1 : ((Number) o).longValue(); }
    static long used(Object o) { return o == null ? -1 : lng(((CompositeData) o).get("used")); }
    static long committed(Object o) { return o == null ? -1 : lng(((CompositeData) o).get("committed")); }
    static void connect() {
        try { if (jc != null) jc.close(); } catch (Exception e) {}
        try { jc = JMXConnectorFactory.connect(new JMXServiceURL(url)); mbs = jc.getMBeanServerConnection(); } catch (Exception e) { jc = null; mbs = null; }
    }
    static final String M = "org.apache.cassandra.metrics:";
    static final String[][] COLS = {
        {"K_requests_size", M + "type=Client,name=RequestsSize", "Value"},
        {"paused_conns", M + "type=Client,name=PausedConnections", "Value"},
        {"conn_paused_count", M + "type=Client,name=ConnectionPaused", "Count"},
        {"req_dispatched", M + "type=Client,name=RequestDispatched", "Count"},
        {"timed_out_before_proc", M + "type=Client,name=TimedOutBeforeProcessing", "Count"},
        {"protocol_exc", M + "type=Client,name=ProtocolException", "Count"},
        {"connected_clients", M + "type=Client,name=ConnectedNativeClients", "Value"},
        {"ntr_active", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks", "Value"},
        {"ntr_pending", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks", "Value"},
        {"ntr_completed", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=CompletedTasks", "Value"},
        {"read_active", M + "type=ThreadPools,path=request,scope=ReadStage,name=ActiveTasks", "Value"},
        {"read_pending", M + "type=ThreadPools,path=request,scope=ReadStage,name=PendingTasks", "Value"},
        {"read_completed", M + "type=ThreadPools,path=request,scope=ReadStage,name=CompletedTasks", "Value"},
        {"read_timeouts", M + "type=ClientRequest,scope=Read,name=Timeouts", "Count"},
        {"range_timeouts", M + "type=ClientRequest,scope=RangeSlice,name=Timeouts", "Count"},
        {"range_count", M + "type=ClientRequest,scope=RangeSlice,name=Latency", "Count"},
    };
    public static void main(String[] a) throws Exception {
        url = "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi";
        long iv = Long.parseLong(a[1]); File out = new File(a[2]);
        PrintWriter csv = new PrintWriter(new FileWriter(new File(out, "samples.csv"), true), true);
        StringBuilder h = new StringBuilder("epoch_ms,heap_used,heap_committed,old_used");
        for (String[] c : COLS) h.append(',').append(c[0]);
        csv.println(h);
        while (true) {
            long t = System.currentTimeMillis();
            if (mbs == null) connect();
            StringBuilder sb = new StringBuilder().append(t);
            if (mbs != null) {
                Object hm = attr("java.lang:type=Memory", "HeapMemoryUsage");
                if (hm == null) { mbs = null; sb.append(",NA,NA,NA"); for (String[] c : COLS) sb.append(",NA"); }
                else {
                    sb.append(',').append(used(hm)).append(',').append(committed(hm)).append(',').append(used(attr("java.lang:type=MemoryPool,name=G1 Old Gen", "Usage")));
                    for (String[] c : COLS) sb.append(',').append(lng(attr(c[1], c[2])));
                }
            } else { sb.append(",NA,NA,NA"); for (String[] c : COLS) sb.append(",NA"); }
            csv.println(sb);
            long sl = iv - (System.currentTimeMillis() - t);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
