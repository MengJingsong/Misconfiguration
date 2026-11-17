// U1 run 2 victim sampler (from run 1's U1Sample + S1Sample's receive-queue query). Runs on V.
// JMX: U = java.nio direct MemoryUsed (JDK Bits counter), heap, MutationStage active/pending/completed, commit-log waits,
//      dropped MUTATION_REQ, networking BufferPool size/overflow, memtable, hints.
// CQL (system_views.internode_inbound on V): K = sum using_bytes (receive-queue capacity in use, on-wire bytes of
//      admitted messages, held until the verb handler returns), reserve bytes, throttled/expired/processed counts.
//   java U1R2Sample <victimIp> <jmxPort> <intervalMs> <outDir>
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;
import java.util.*;

public class U1R2Sample {
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
        {"cl_wait_seg_count", M + "type=CommitLog,name=WaitingOnSegmentAllocation", "Count"},
        {"cl_wait_commit_count", M + "type=CommitLog,name=WaitingOnCommit", "Count"},
        {"cl_pending", M + "type=CommitLog,name=PendingTasks", "Value"},
        {"cl_total_size", M + "type=CommitLog,name=TotalCommitLogSize", "Value"},
        {"dropped_mut", M + "type=DroppedMessage,scope=MUTATION_REQ,name=Dropped", "Count"},
        {"dropped_hint", M + "type=DroppedMessage,scope=HINT_REQ,name=Dropped", "Count"},
        {"memtable_onheap", M + "type=Table,keyspace=u1r2,scope=t,name=AllMemtablesHeapSize", "Value"},
        {"pending_flushes", M + "type=Table,keyspace=u1r2,scope=t,name=PendingFlushes", "Count"},
        {"local_writes", M + "type=Table,keyspace=u1r2,scope=t,name=WriteLatency", "Count"},
        {"net_pool_size", M + "type=BufferPool,scope=networking,name=Size", "Value"},
        {"net_pool_overflow", M + "type=BufferPool,scope=networking,name=OverflowSize", "Value"},
        {"memtable_flush_pending", M + "type=ThreadPools,path=internal,scope=MemtableFlushWriter,name=PendingTasks", "Value"},
    };
    public static void main(String[] a) throws Exception {
        String ip = a[0]; url = "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[1] + "/jmxrmi";
        long iv = Long.parseLong(a[2]); File out = new File(a[3]);
        PrintWriter csv = new PrintWriter(new FileWriter(new File(out, "samples.csv"), true), true);
        PrintWriter peers = new PrintWriter(new FileWriter(new File(out, "peers.txt"), true), true);
        StringBuilder h = new StringBuilder("epoch_ms,heap_used");
        for (String[] c : COLS) h.append(',').append(c[0]);
        h.append(",K_using,K_reserve,peers_using,max_peer_using,throttled,received,processed,expired,expired_bytes,cql_ms");
        csv.println(h);
        Cluster cl = null; Session s = null;
        String q = "SELECT address,using_bytes,using_reserve_bytes,throttled_count,received_count,processed_count,expired_count,expired_bytes FROM system_views.internode_inbound";
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
            String cq = "NA,NA,NA,NA,NA,NA,NA,NA,NA,NA";
            long c0 = System.currentTimeMillis();
            try {
                if (s == null) {
                    cl = Cluster.builder().addContactPoint(ip).withProtocolVersion(ProtocolVersion.V4)
                        .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                            Collections.singletonList(new java.net.InetSocketAddress(ip, 9042))))
                        .withSocketOptions(new SocketOptions().setReadTimeoutMillis(3000).setConnectTimeoutMillis(2000))
                        .withoutJMXReporting().build();
                    s = cl.connect();
                }
                long u = 0, r = 0, th = 0, rc = 0, pc = 0, ec = 0, eb = 0, mx = 0; int np = 0;
                StringBuilder pb = new StringBuilder("@ " + t + "\n");
                for (Row row : s.execute(q)) {
                    long uu = row.getLong(1); u += uu; r += row.getLong(2); th += row.getLong(3); rc += row.getLong(4);
                    pc += row.getLong(5); ec += row.getLong(6); eb += row.getLong(7);
                    if (uu > 0) np++; if (uu > mx) mx = uu;
                    pb.append(row.getInet(0).getHostAddress()).append(' ').append(uu).append(' ').append(row.getLong(2)).append(' ')
                      .append(row.getLong(3)).append(' ').append(row.getLong(4)).append(' ').append(row.getLong(5)).append(' ').append(row.getLong(6)).append('\n');
                }
                peers.print(pb);
                cq = u + "," + r + "," + np + "," + mx + "," + th + "," + rc + "," + pc + "," + ec + "," + eb + "," + (System.currentTimeMillis() - c0);
            } catch (Exception e) {
                try { if (cl != null) cl.close(); } catch (Exception x) {}
                cl = null; s = null;
            }
            csv.println(sb + "," + cq);
            long sl = iv - (System.currentTimeMillis() - t);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
