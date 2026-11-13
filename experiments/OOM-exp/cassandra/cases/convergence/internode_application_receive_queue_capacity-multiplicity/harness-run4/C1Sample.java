// C1 run-4 victim sampler: JMX (direct buffers = U, heap, MutationStage, Cassandra BufferPool metrics)
// + CQL system_views.internode_inbound (K = sum using_bytes, reserve, throttled, received/processed/expired).
//   java C1Sample <victimIp> <jmxPort> <intervalMs> <outDir>
// Writes <outDir>/samples.csv (one line per tick) and <outDir>/peers.txt (per-peer rows each tick).
// Keeps going (writing NA) when the victim is down, so the time of death is visible.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;
import java.util.*;

public class C1Sample {
    static MBeanServerConnection mbs;
    static JMXConnector jc;
    static String url;
    static Object attr(String on, String a) {
        try { return mbs.getAttribute(new ObjectName(on), a); } catch (Exception e) { return null; }
    }
    static long lng(Object o) { return o == null ? -1 : ((Number) o).longValue(); }
    static void connect() {
        try { if (jc != null) jc.close(); } catch (Exception e) {}
        try { jc = JMXConnectorFactory.connect(new JMXServiceURL(url)); mbs = jc.getMBeanServerConnection(); }
        catch (Exception e) { jc = null; mbs = null; }
    }
    public static void main(String[] a) throws Exception {
        String ip = a[0]; url = "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[1] + "/jmxrmi";
        long iv = Long.parseLong(a[2]); File out = new File(a[3]);
        PrintWriter csv = new PrintWriter(new FileWriter(new File(out, "samples.csv"), true), true);
        PrintWriter peers = new PrintWriter(new FileWriter(new File(out, "peers.txt"), true), true);
        csv.println("epoch_ms,direct_used,direct_count,heap_used,mut_pending,mut_active,net_pool_size,net_pool_overflow,cc_pool_size,K_using,K_reserve,peers_using,max_peer_using,throttled,received,processed,expired,expired_bytes,received_bytes,processed_bytes,cql_ms");
        Cluster cl = null; Session s = null;
        String q = "SELECT address,using_bytes,using_reserve_bytes,throttled_count,received_count,processed_count,expired_count,expired_bytes,received_bytes,processed_bytes FROM system_views.internode_inbound";
        while (true) {
            long t = System.currentTimeMillis();
            if (mbs == null) connect();
            String jmx;
            if (mbs != null) {
                long du = lng(attr("java.nio:type=BufferPool,name=direct", "MemoryUsed"));
                long dc = lng(attr("java.nio:type=BufferPool,name=direct", "Count"));
                Object hm = attr("java.lang:type=Memory", "HeapMemoryUsage");
                long hu = hm == null ? -1 : lng(((CompositeData) hm).get("used"));
                long mp = lng(attr("org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks", "Value"));
                long ma = lng(attr("org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=ActiveTasks", "Value"));
                long ns = lng(attr("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size", "Value"));
                long no = lng(attr("org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=OverflowSize", "Value"));
                long cs = lng(attr("org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size", "Value"));
                if (du < 0 && hu < 0) { mbs = null; }
                jmx = du + "," + dc + "," + hu + "," + mp + "," + ma + "," + ns + "," + no + "," + cs;
            } else jmx = "NA,NA,NA,NA,NA,NA,NA,NA";
            String cq = "NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA,NA";
            long c0 = System.currentTimeMillis();
            try {
                if (s == null) {
                    cl = Cluster.builder().addContactPoint(ip).withProtocolVersion(ProtocolVersion.V4)
                        .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                            Collections.singletonList(new java.net.InetSocketAddress(ip, 9042))))
                        .withSocketOptions(new SocketOptions().setReadTimeoutMillis(5000).setConnectTimeoutMillis(2000))
                        .withoutJMXReporting().build();
                    s = cl.connect();
                }
                long u = 0, r = 0, th = 0, rc = 0, pc = 0, ec = 0, eb = 0, rb = 0, pb = 0, mx = 0; int np = 0;
                StringBuilder sb = new StringBuilder("@ " + t + "\n");
                for (Row row : s.execute(q)) {
                    long uu = row.getLong(1); u += uu; r += row.getLong(2); th += row.getLong(3); rc += row.getLong(4);
                    pc += row.getLong(5); ec += row.getLong(6); eb += row.getLong(7); rb += row.getLong(8); pb += row.getLong(9);
                    if (uu > 0) np++; if (uu > mx) mx = uu;
                    sb.append(row.getInet(0).getHostAddress()).append(' ').append(uu).append(' ').append(row.getLong(2)).append(' ')
                      .append(row.getLong(3)).append(' ').append(row.getLong(4)).append(' ').append(row.getLong(5)).append(' ').append(row.getLong(6)).append('\n');
                }
                peers.print(sb);
                cq = u + "," + r + "," + np + "," + mx + "," + th + "," + rc + "," + pc + "," + ec + "," + eb + "," + rb + "," + pb + "," + (System.currentTimeMillis() - c0);
            } catch (Exception e) {
                try { if (cl != null) cl.close(); } catch (Exception x) {}
                cl = null; s = null;
            }
            csv.println(t + "," + jmx + "," + cq);
            long sl = iv - (System.currentTimeMillis() - t);
            if (sl > 0) Thread.sleep(sl);
        }
    }
}
