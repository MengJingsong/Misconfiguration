// U1 victim sampler (derived from S1Sample/C1Sample, JMX only). One line per tick into <outDir>/samples.csv.
// U = java.nio direct MemoryUsed (JDK Bits counter; no Cassandra counter K covers the in-flight DOB fill).
//   java U1Sample <jmxPort> <intervalMs> <outDir>
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

public class U1Sample {
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
        {"mut_pending", M + "type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks", "Value"},
        {"mut_active", M + "type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks", "Value"},
        {"mut_completed", M + "type=ThreadPools,path=request,scope=MutationStage,name=CompletedTasks", "Value"},
        {"ntr_active", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks", "Value"},
        {"ntr_pending", M + "type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks", "Value"},
        {"cl_wait_seg_count", M + "type=CommitLog,name=WaitingOnSegmentAllocation", "Count"},
        {"cl_wait_commit_count", M + "type=CommitLog,name=WaitingOnCommit", "Count"},
        {"cl_pending", M + "type=CommitLog,name=PendingTasks", "Value"},
        {"cl_total_size", M + "type=CommitLog,name=TotalCommitLogSize", "Value"},
        {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped", "Count"},
        {"write_timeouts", M + "type=ClientRequest,scope=Write,name=Timeouts", "Count"},
        {"write_count", M + "type=ClientRequest,scope=Write,name=Latency", "Count"},
        {"memtable_onheap", M + "type=Table,keyspace=u1,scope=t,name=AllMemtablesHeapSize", "Value"},
        {"pending_flushes", M + "type=Table,keyspace=u1,scope=t,name=PendingFlushes", "Count"},
        {"hints_inprogress", M + "type=Storage,name=TotalHintsInProgress", "Count"},
        {"net_pool_size", M + "type=BufferPool,scope=networking,name=Size", "Value"},
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
