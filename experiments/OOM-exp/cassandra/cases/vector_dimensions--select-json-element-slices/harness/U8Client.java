// U8 client (ms0640, loopback). Java driver 3.12.1 (shaded), protocol V4, CL ONE, metadata disabled
// (driver 3 cannot parse vector<...> schema strings).
//   java U8Client load   <host> <D>          schema + one row pk=0 with a D-byte zero vector<boolean, D> (all false)
//   java U8Client verify <host>              SELECT v ... pk=0 once; prints the value length
//   java U8Client run    <host> <json|plain> <N> <R>
// run: N separate Cluster objects (one connection each), a CyclicBarrier(N) per round, R rounds.
// json = SELECT JSON v FROM u8.t WHERE pk = 0; plain = SELECT v FROM u8.t WHERE pk = 0.
// One CSV line per request: start_ms,end_ms,thread,round,resp_len,error  (the JSON is never decoded to a String).
// Ends when R rounds finish, or when every thread has seen a connection-level error (node unreachable).
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U8Client {
    static Cluster cluster(String host) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1);
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withQueryOptions(new QueryOptions().setMetadataEnabled(false).setConsistencyLevel(ConsistencyLevel.ONE))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("load")) {
            int d = Integer.parseInt(a[2]);
            try (Cluster c = cluster(host); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u8 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS u8.t (pk int PRIMARY KEY, v vector<boolean, " + d + ">)");
                PreparedStatement ps = s.prepare("INSERT INTO u8.t (pk, v) VALUES (0, ?)");
                BoundStatement b = ps.bind();
                b.setBytesUnsafe(0, ByteBuffer.wrap(new byte[d]));
                long t0 = System.currentTimeMillis();
                s.execute(b);
                System.out.println("load ok D=" + d + " ms=" + (System.currentTimeMillis() - t0));
            }
            return;
        }
        if (a[0].equals("verify")) {
            try (Cluster c = cluster(host); Session s = c.connect()) {
                Row r = s.execute("SELECT v FROM u8.t WHERE pk = 0").one();
                System.out.println("verify len=" + (r == null ? -1 : r.getBytesUnsafe(0).remaining()));
            }
            return;
        }
        if (a[0].equals("run")) {
            String mode = a[2]; int n = Integer.parseInt(a[3]), rounds = Integer.parseInt(a[4]);
            String q = mode.equals("json") ? "SELECT JSON v FROM u8.t WHERE pk = 0" : "SELECT v FROM u8.t WHERE pk = 0";
            Cluster[] cs = new Cluster[n]; Session[] ss = new Session[n];
            for (int i = 0; i < n; i++) { cs[i] = cluster(host); ss[i] = cs[i].connect(); }
            System.out.println("start_ms,end_ms,thread,round,resp_len,error");
            System.out.flush();
            AtomicBoolean down = new AtomicBoolean(false);
            CyclicBarrier bar = new CyclicBarrier(n);
            Thread[] ts = new Thread[n];
            AtomicInteger ok = new AtomicInteger(), err = new AtomicInteger();
            for (int i = 0; i < n; i++) {
                final int id = i;
                ts[i] = new Thread(() -> {
                    for (int r = 0; r < rounds && !down.get(); r++) {
                        try { bar.await(300, TimeUnit.SECONDS); } catch (Exception e) { break; }
                        long t0 = System.currentTimeMillis(); long len = -1; String e = "";
                        try {
                            Row row = ss[id].execute(q).one();
                            ByteBuffer bb = row == null ? null : row.getBytesUnsafe(0);
                            len = bb == null ? -1 : bb.remaining();
                            ok.incrementAndGet();
                        } catch (Throwable x) {
                            e = x.getClass().getSimpleName() + ":" + String.valueOf(x.getMessage()).replace(',', ';').replace('\n', ' ');
                            if (e.length() > 200) e = e.substring(0, 200);
                            err.incrementAndGet();
                            // amended 2026-11-18 14:50 EST: a client-side timeout (OperationTimedOutException) no longer
                            // ends the run; only an unreachable node does (the frozen design: "Exit when R rounds finish
                            // or the node is unreachable"). Runs before B-8G-N11-2 used the earlier rule.
                            if (x instanceof com.datastax.driver.core.exceptions.NoHostAvailableException
                                || x instanceof com.datastax.driver.core.exceptions.TransportException) {
                                down.set(true); bar.reset();
                            }
                        }
                        synchronized (System.out) {
                            System.out.println(t0 + "," + System.currentTimeMillis() + "," + id + "," + r + "," + len + "," + e);
                            System.out.flush();
                        }
                    }
                });
                ts[i].start();
            }
            for (Thread t : ts) t.join();
            System.out.println("SUMMARY ok=" + ok.get() + " err=" + err.get() + " down=" + down.get());
            System.out.flush();
            for (int i = 0; i < n; i++) { try { cs[i].closeAsync(); } catch (Throwable t) {} }
            System.exit(0);
        }
    }
}
