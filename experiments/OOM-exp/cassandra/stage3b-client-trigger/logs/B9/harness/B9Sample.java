// B9 3-b confirm sampler (stage-2 B9Sample + ProtocolException/AuthSuccess/AuthFailure columns).
// B9 victim sampler (derived from U1Sample, JMX only). One line per tick into <outDir>/samples.csv.
// K = Client.RequestsSize (the in-flight limit's global counter); JDK direct = java.nio BufferPool direct (Bits counter).
//   java B9Sample <jmxPort> <intervalMs> <outDir>
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class B9Sample {
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
        {"K_requests_size", M + "type=Client,name=RequestsSize", "Value"},
        {"paused_conns", M + "type=Client,name=PausedConnections", "Value"},
        {"connected_clients", M + "type=Client,name=ConnectedNativeClients", "Value"},
        {"conn_paused_count", M + "type=Client,name=ConnectionPaused", "Count"},
        {"req_dispatched", M + "type=Client,name=RequestDispatched", "Count"},
        {"timed_out_before_proc", M + "type=Client,name=TimedOutBeforeProcessing", "Count"},
        {"ntr_active", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks", "Value"},
        {"ntr_pending", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks", "Value"},
        {"mut_active", M + "type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks", "Value"},
        {"mut_pending", M + "type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks", "Value"},
        {"mut_completed", M + "type=ThreadPools,path=request,scope=MutationStage,name=CompletedTasks", "Value"},
        {"write_timeouts", M + "type=ClientRequest,scope=Write,name=Timeouts", "Count"},
        {"write_count", M + "type=ClientRequest,scope=Write,name=Latency", "Count"},
        {"memtable_onheap", M + "type=Table,keyspace=b9,scope=t,name=AllMemtablesHeapSize", "Value"},
        {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped", "Count"},
        {"protocol_exc", M + "type=Client,name=ProtocolException", "Count"},
        {"auth_success", M + "type=Client,name=AuthSuccess", "Count"},
        {"auth_failure", M + "type=Client,name=AuthFailure", "Count"},
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
