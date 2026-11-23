// U12 client (stage 2). Java driver 3.12.1 (Cassandra's lib), native protocol v4, one connection, one request in flight.
//   java U12Load schema <host>
//   java U12Load write <host> <ck> <kFrom> <kTo>     writes k = kFrom..kTo-1:  UPDATE u12.t SET m = m + {k: 1 MiB urandom} WHERE pk=0 AND ck=<ck>
//        -Dstop_on_error=true (default; golden builds) | false (arm N: count failures, keep going until kTo or 20 consecutive failures)
// Prints one line per 10 acks and a final "acked=<n> failed=<m>" line.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.security.SecureRandom;
import java.util.*;

public class U12Load {
    static Cluster cluster(String host) {
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(10000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting().build();
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u12 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS u12.t (pk int, ck int, m map<int, blob>, PRIMARY KEY (pk, ck))");
                System.out.println("schema ok");
            }
            return;
        }
        int ck = Integer.parseInt(a[2]), from = Integer.parseInt(a[3]), to = Integer.parseInt(a[4]);
        boolean stopOnError = Boolean.parseBoolean(System.getProperty("stop_on_error", "true"));
        SecureRandom rnd = new SecureRandom();
        long ok = 0, fail = 0; int consec = 0;
        Cluster c = cluster(host); Session s = c.connect();
        PreparedStatement ps = s.prepare("UPDATE u12.t SET m = m + ? WHERE pk = ? AND ck = ?");
        ps.setConsistencyLevel(ConsistencyLevel.ONE);
        byte[] v = new byte[1048576];
        for (int k = from; k < to; k++) {
            rnd.nextBytes(v);
            Map<Integer, ByteBuffer> m = new HashMap<>();
            m.put(k, ByteBuffer.wrap(v.clone()));
            try {
                s.execute(ps.bind(m, 0, ck));
                ok++; consec = 0;
                if (ok % 10 == 0) System.out.println(System.currentTimeMillis() + " acked=" + ok + " k=" + k);
            } catch (Exception e) {
                fail++; consec++;
                System.out.println(System.currentTimeMillis() + " FAIL k=" + k + " " + e.getClass().getSimpleName() + ": " + e.getMessage());
                if (stopOnError || consec >= 20) break;
                try { Thread.sleep(1000); } catch (InterruptedException ie) { break; }
            }
        }
        System.out.println(System.currentTimeMillis() + " acked=" + ok + " failed=" + fail);
        try { c.close(); } catch (Exception e) {}
        System.exit(fail == 0 ? 0 : 1);
    }
}
