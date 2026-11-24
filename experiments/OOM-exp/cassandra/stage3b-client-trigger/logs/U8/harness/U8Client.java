// U8 client (ms0640, loopback). Java driver 3.12.1 (shaded), protocol V4, CL ONE, metadata disabled
// (driver 3 cannot parse vector<...> schema strings).
// 3-b confirm (2026-11-23): every mode logs in with -Du8.user / -Du8.pass (PasswordAuthenticator); empty user = no credentials.
//   java U8Client load   <host> <D>          schema + one row pk=0 with a D-byte zero vector<boolean, D> (all false)
//   java U8Client verify <host>              SELECT v ... pk=0 once; prints the value length
//   java U8Client run    <host> <json|plain> <N> <R>
//   java U8Client su     <host> <file>       (superuser) run each non-empty line of <file> as a statement, print result rows;
//                                            waits up to 120 s for the superuser login to exist
//   java U8Client try    <host> <stmt>       run one statement as -Du8.user, print OK/rows or the exception class + message
//   java U8Client victim <host> <rate/s> <stopfile> <out.csv>   victim workload on victimks.kv
// run: N separate Cluster objects (one connection each), a CyclicBarrier(N) per round, R rounds.
// json = SELECT JSON v FROM u8.t WHERE pk = 0; plain = SELECT v FROM u8.t WHERE pk = 0.
// One CSV line per request: start_ms,end_ms,thread,round,resp_len,error  (the JSON is never decoded to a String).
// Ends when R rounds finish, or when every thread has seen a connection-level error (node unreachable).
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U8Client {
    static Cluster cluster(String host) { return cluster(host, 120000); }
    static Cluster cluster(String host, int readTimeoutMs) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1);
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(readTimeoutMs).setConnectTimeoutMillis(30000))
            .withQueryOptions(new QueryOptions().setMetadataEnabled(false).setConsistencyLevel(ConsistencyLevel.ONE))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withReconnectionPolicy(new ConstantReconnectionPolicy(1000))
            .withPoolingOptions(po).withoutJMXReporting();
        String u = System.getProperty("u8.user", ""), p = System.getProperty("u8.pass", "");
        if (!u.isEmpty()) b = b.withCredentials(u, p);
        return b.build();
    }
    static String err(Throwable x) {
        String e = x.getClass().getSimpleName() + ":" + String.valueOf(x.getMessage()).replace(',', ';').replace('\n', ' ');
        return e.length() > 300 ? e.substring(0, 300) : e;
    }
    static void printRows(ResultSet rs) {
        for (Row r : rs) {
            StringBuilder sb = new StringBuilder("  row:");
            for (int i = 0; i < r.getColumnDefinitions().size(); i++) {
                ByteBuffer bb = r.getBytesUnsafe(i);
                String s;
                try { s = String.valueOf(r.getObject(i)); } catch (Throwable t) { s = bb == null ? "null" : ("<" + bb.remaining() + " B>"); }
                sb.append(' ').append(r.getColumnDefinitions().getName(i)).append('=').append(s);
            }
            System.out.println(sb);
        }
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        System.out.println("# as user=" + System.getProperty("u8.user", "") );
        if (a[0].equals("su")) {
            List<String> lines = Files.readAllLines(Paths.get(a[2]));
            Cluster c = null; Session s = null;
            long until = System.currentTimeMillis() + 120000;
            while (true) {
                try { c = cluster(host, 30000); s = c.connect(); break; }
                catch (Throwable t) {
                    if (c != null) c.close();
                    if (System.currentTimeMillis() > until) throw t;
                    System.out.println("# login not ready: " + err(t)); Thread.sleep(3000);
                }
            }
            for (String l : lines) {
                l = l.trim(); if (l.isEmpty() || l.startsWith("#")) continue;
                System.out.println("> " + l);
                try { printRows(s.execute(l)); System.out.println("  OK"); }
                catch (Throwable t) { System.out.println("  FAIL " + err(t)); }
            }
            c.close(); return;
        }
        if (a[0].equals("try")) {
            String st = a[2];
            System.out.println("> " + st);
            try (Cluster c = cluster(host, 30000); Session s = c.connect()) {
                try { printRows(s.execute(st)); System.out.println("  RESULT OK"); }
                catch (Throwable t) { System.out.println("  RESULT FAIL " + err(t)); }
            } catch (Throwable t) { System.out.println("  RESULT CONNECT-FAIL " + err(t)); }
            return;
        }
        if (a[0].equals("victim")) {
            double rate = Double.parseDouble(a[2]); File stop = new File(a[3]);
            PrintWriter out = new PrintWriter(new FileWriter(a[4], true), false);
            out.println("issue_ms,end_ms,op,result"); out.flush();
            Cluster c = cluster(host, 10000); Session s = c.connect();
            PreparedStatement ins = s.prepare("INSERT INTO victimks.kv (k, v) VALUES (?, ?)");
            PreparedStatement sel = s.prepare("SELECT v FROM victimks.kv WHERE k = ?");
            byte[] blob = new byte[100];
            AtomicLong seq = new AtomicLong();
            ScheduledExecutorService ex = Executors.newSingleThreadScheduledExecutor();
            long periodUs = (long) (1e6 / rate);
            ex.scheduleAtFixedRate(() -> {
                long i = seq.getAndIncrement(); int k = (int) ((i / 2) % 1000);
                final boolean w = (i % 2 == 0);
                final long t0 = System.currentTimeMillis();
                try {
                    ResultSetFuture f = w ? s.executeAsync(ins.bind(k, ByteBuffer.wrap(blob))) : s.executeAsync(sel.bind(k));
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet r) { synchronized (out) { out.println(t0 + "," + System.currentTimeMillis() + "," + (w ? "W" : "R") + ",ok"); } }
                        public void onFailure(Throwable t) { synchronized (out) { out.println(t0 + "," + System.currentTimeMillis() + "," + (w ? "W" : "R") + "," + err(t)); } }
                    }, MoreExecutors.directExecutor());
                } catch (Throwable t) { synchronized (out) { out.println(t0 + "," + System.currentTimeMillis() + "," + (w ? "W" : "R") + "," + err(t)); } }
            }, 0, periodUs, TimeUnit.MICROSECONDS);
            while (!stop.exists()) { Thread.sleep(500); synchronized (out) { out.flush(); } }
            ex.shutdownNow(); Thread.sleep(11000);
            synchronized (out) { out.flush(); out.close(); }
            try { c.closeAsync(); } catch (Throwable t) {}
            System.exit(0);
        }
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
                            e = err(x);
                            if (e.length() > 200) e = e.substring(0, 200);
                            err.incrementAndGet();
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
