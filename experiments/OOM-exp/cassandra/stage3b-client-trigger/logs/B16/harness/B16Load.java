// B16 3-b confirm client (ms0611, 2026-11-23): the stage-2 B16Load plus credentials (env B16_USER / B16_PASS ->
// PlainTextAuthProvider; no env = no credentials) and the modes admin-setup / authcheck (below). The query paths
// (schema, load, one, run) are unchanged from stage 2. Stage-2 header follows.
// B16 load/read client (ms0611, loopback), adapted from U4Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE.
//   java B16Load schema <host>
//   java B16Load load  <host> <tbl> <ranges> <boundBytes> <batch> <inflight>
//        for i in 0..ranges-1: DELETE FROM b16.<tbl> WHERE pk=0 AND ck >= start_i AND ck <= end_i,
//        start_i = %06d(i) + "a" + "x"*(s-7), end_i = %06d(i) + "b" + "x"*(s-7)  (disjoint: 2 markers per range)
//        sent as UNLOGGED single-partition batches of <batch>, <inflight> batches in flight, prepared, CL ONE.
//   java B16Load one   <host> <tbl>        one read; prints rows, latency, error class and message, warnings
//   java B16Load run   <host> <conns> <warmTbl> <warmSecs> <tbl> <steps "c:secs,...">
//        closed loop: warm-up 1 read in flight on <warmTbl> for <warmSecs> (step label "w"), then the steps on <tbl>.
//        prepared SELECT * FROM b16.<tbl> WHERE pk = 0, fetch size 5000 (driver default, set explicitly), first page.
// Per-second CSV:  t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,eTimeout,eTomb,eSize,eOther,lastErr
// (MBps is always 0: responses have 0 rows; kept for steps.py compatibility.)
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B16Load {
    static Cluster cluster(String host, int conns) { return cluster(host, conns, System.getenv("B16_USER"), System.getenv("B16_PASS")); }
    static Cluster cluster(String host, int conns, String user, String pass) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        Cluster.Builder cb = Cluster.builder();
        if (user != null && !user.isEmpty()) cb = cb.withCredentials(user, pass);
        return cb.addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    static String bound(int i, char c, int s) {
        StringBuilder b = new StringBuilder(s);
        b.append(String.format("%06d", i)).append(c);
        while (b.length() < s) b.append('x');
        return b.toString();
    }

    // error class: 0 timeout, 1 tombstones, 2 read size, 3 other
    static int klass(Throwable e) {
        if (e instanceof ReadTimeoutException) return 0;
        if (e instanceof ReadFailureException) {
            Map<java.net.InetAddress, Integer> m = ((ReadFailureException) e).getFailuresMap();
            if (m != null) for (Integer v : m.values()) { if (v != null && v == 1) return 1; if (v != null && v == 4) return 2; }
            String s = String.valueOf(e.getMessage());
            if (s.contains("TOMBSTONE")) return 1;
            if (s.contains("READ_SIZE")) return 2;
        }
        return 3;
    }

    static String msg(Throwable e) {
        String x = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
        if (e instanceof ReadFailureException) x += " failures=" + ((ReadFailureException) e).getFailuresMap();
        return x.replace(',', ';').replace('\n', ' ');
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("admin-setup")) { adminSetup(host); return; }
        if (a[0].equals("authcheck")) { authCheck(host); return; }
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b16 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS b16.t (pk int, ck text, v int, PRIMARY KEY (pk, ck))");
                s.execute("CREATE TABLE IF NOT EXISTS b16.m (pk int, ck text, v int, PRIMARY KEY (pk, ck))");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("load")) {
            String tbl = a[2]; int ranges = Integer.parseInt(a[3]), s = Integer.parseInt(a[4]);
            int batch = Integer.parseInt(a[5]), inflight = Integer.parseInt(a[6]);
            try (Cluster c = cluster(host, 2); Session ss = c.connect()) {
                PreparedStatement ps = ss.prepare("DELETE FROM b16." + tbl + " WHERE pk = 0 AND ck >= ? AND ck <= ?");
                Semaphore sem = new Semaphore(inflight); AtomicLong err = new AtomicLong(), done = new AtomicLong();
                long t0 = System.currentTimeMillis();
                for (int i = 0; i < ranges; i += batch) {
                    BatchStatement b = new BatchStatement(BatchStatement.Type.UNLOGGED);
                    for (int k = i; k < Math.min(ranges, i + batch); k++) b.add(ps.bind(bound(k, 'a', s), bound(k, 'b', s)));
                    b.setConsistencyLevel(ConsistencyLevel.ONE);
                    sem.acquireUninterruptibly();
                    ResultSetFuture f = ss.executeAsync(b);
                    final int n = b.size();
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet x) { done.addAndGet(n); sem.release(); }
                        public void onFailure(Throwable e) { err.incrementAndGet(); System.out.println("load err " + msg(e)); sem.release(); }
                    }, MoreExecutors.directExecutor());
                    if ((i / batch) % 250 == 0) System.out.println("load " + tbl + " sent=" + i + " done=" + done.get() + " err=" + err.get()
                                                                    + " s=" + (System.currentTimeMillis() - t0) / 1000);
                }
                sem.acquireUninterruptibly(inflight);
                System.out.println("load ok tbl=" + tbl + " ranges=" + ranges + " boundBytes=" + s + " done=" + done.get()
                                   + " errors=" + err.get() + " secs=" + (System.currentTimeMillis() - t0) / 1000);
            }
            return;
        }
        if (a[0].equals("one")) {
            String tbl = a[2];
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                long t0 = System.nanoTime();
                try {
                    PreparedStatement ps = s.prepare("SELECT * FROM b16." + tbl + " WHERE pk = 0");
                    ps.setConsistencyLevel(ConsistencyLevel.ONE);
                    BoundStatement bs = ps.bind(); bs.setFetchSize(5000);
                    ResultSet rs = s.execute(bs);
                    int n = rs.getAvailableWithoutFetching();
                    System.out.println("one tbl=" + tbl + " OK rows=" + n + " ms=" + (System.nanoTime() - t0) / 1000000
                                       + " fullyFetched=" + rs.isFullyFetched() + " warnings=" + rs.getExecutionInfo().getWarnings());
                } catch (Exception e) {
                    System.out.println("one tbl=" + tbl + " ERROR ms=" + (System.nanoTime() - t0) / 1000000 + " " + msg(e));
                }
            }
            return;
        }
        // run
        int conns = Integer.parseInt(a[2]); String warmTbl = a[3]; int warmSecs = Integer.parseInt(a[4]);
        String tbl = a[5]; String[] steps = a[6].split(",");
        Cluster c = cluster(host, conns); Session s = c.connect();
        PreparedStatement pw = s.prepare("SELECT * FROM b16." + warmTbl + " WHERE pk = 0");
        PreparedStatement pt = s.prepare("SELECT * FROM b16." + tbl + " WHERE pk = 0");
        pw.setConsistencyLevel(ConsistencyLevel.ONE); pt.setConsistencyLevel(ConsistencyLevel.ONE);
        AtomicReference<PreparedStatement> cur = new AtomicReference<>(pw);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong();
        AtomicLongArray ek = new AtomicLongArray(4);
        AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        AtomicReference<String> label = new AtomicReference<>("w");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        Semaphore sem = new Semaphore(0);
        AtomicBoolean stop = new AtomicBoolean(false);
        Thread gen = new Thread(() -> {
            while (!stop.get()) {
                try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                if (stop.get()) { sem.release(); return; }
                inflight.incrementAndGet();
                final long t0 = System.nanoTime();
                BoundStatement bs = cur.get().bind(); bs.setFetchSize(5000);
                ResultSetFuture f = s.executeAsync(bs);
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        rowsLast.set(rs.getAvailableWithoutFetching()); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000);
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        err.incrementAndGet(); ek.incrementAndGet(klass(e)); lastErr.set(msg(e));
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,eTimeout,eTomb,eSize,eOther,lastErr");
        long tStart = System.currentTimeMillis();
        Thread pr = new Thread(() -> {
            long lastOk = 0;
            try {
                while (true) {
                    Thread.sleep(1000);
                    long o = ok.get();
                    List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
                    Collections.sort(l);
                    double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
                    System.out.printf("%d,%s,%d,%d,%d,%d,0.0,%.1f,%.1f,%d,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), label.get(), inflight.get(), o, err.get(),
                                      o - lastOk, p50, p99, rowsLast.get(), ek.get(0), ek.get(1), ek.get(2), ek.get(3), lastErr.getAndSet(""));
                    lastOk = o;
                }
            } catch (InterruptedException e) { }
        });
        pr.setDaemon(true); pr.start();
        int target = 0;
        if (warmSecs > 0) { sem.release(1); target = 1; Thread.sleep(warmSecs * 1000L); }
        // switch tables: take back the warm-up permit (waits for the warm-up read in flight to finish)
        if (target > 0) { sem.acquireUninterruptibly(target); target = 0; }
        cur.set(pt);
        for (String st : steps) {
            String[] kv = st.split(":"); int n = Integer.parseInt(kv[0]); long secs = Long.parseLong(kv[1]);
            label.set(String.valueOf(n));
            int d = n - target; target = n;
            if (d > 0) sem.release(d); else if (d < 0) sem.acquireUninterruptibly(-d);
            Thread.sleep(secs * 1000L);
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        Thread.sleep(1100);
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d eTimeout=%d eTomb=%d eSize=%d eOther=%d inflight_left=%d%n", (System.currentTimeMillis() - tStart) / 1000.0,
                          ok.get(), err.get(), ek.get(0), ek.get(1), ek.get(2), ek.get(3), inflight.get());
        c.closeAsync(); System.exit(0);
    }

    // ---- 3-b confirm additions ----
    static final String[][] ROLES = { {"attacker", "atk-3b-B16"}, {"tenant", "ten-3b-B16"}, {"reader", "rd-3b-B16"} };

    // superuser (default role cassandra, created by CassandraRoleManager ~10 s after the first start): roles, the admin
    // schema (b16.t, b16.m as in stage 2; vic.kv for the victim tenant), grants; then the grants and role flags as stored.
    static void adminSetup(String host) throws Exception {
        Cluster c = null; Session s = null;
        for (int i = 0; i < 60 && s == null; i++) {
            try { c = cluster(host, 1, "cassandra", "cassandra"); s = c.connect(); }
            catch (Exception e) { if (c != null) c.close(); c = null; System.out.println("admin login retry " + i + ": " + msg(e)); Thread.sleep(2000); }
        }
        String[] st = {
            "CREATE ROLE IF NOT EXISTS attacker WITH PASSWORD = 'atk-3b-B16' AND LOGIN = true AND SUPERUSER = false",
            "CREATE ROLE IF NOT EXISTS tenant WITH PASSWORD = 'ten-3b-B16' AND LOGIN = true AND SUPERUSER = false",
            "CREATE ROLE IF NOT EXISTS reader WITH PASSWORD = 'rd-3b-B16' AND LOGIN = true AND SUPERUSER = false",
            "CREATE KEYSPACE IF NOT EXISTS b16 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
            "CREATE TABLE IF NOT EXISTS b16.t (pk int, ck text, v int, PRIMARY KEY (pk, ck))",
            "CREATE TABLE IF NOT EXISTS b16.m (pk int, ck text, v int, PRIMARY KEY (pk, ck))",
            "CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
            "CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v text)",
            "GRANT SELECT ON TABLE b16.t TO attacker", "GRANT MODIFY ON TABLE b16.t TO attacker",
            "GRANT SELECT ON TABLE b16.m TO attacker", "GRANT MODIFY ON TABLE b16.m TO attacker",
            "GRANT SELECT ON TABLE vic.kv TO tenant", "GRANT MODIFY ON TABLE vic.kv TO tenant",
            "GRANT SELECT ON TABLE b16.t TO reader" };
        for (String q : st) { s.execute(q); System.out.println("admin: " + q.replaceAll("PASSWORD = '[^']*'", "PASSWORD = '…'")); }
        for (String r : new String[] {"attacker", "tenant", "reader"})
            for (Row x : s.execute("LIST ALL PERMISSIONS OF " + r))
                System.out.println("perm " + r + ": " + x.getString("resource") + " " + x.getString("permission"));
        for (Row x : s.execute("SELECT role, is_superuser, can_login, member_of FROM system_auth.roles"))
            System.out.println("role " + x.getString(0) + " superuser=" + x.getBool(1) + " login=" + x.getBool(2) + " member_of=" + x.getSet(3, String.class));
        c.close();
    }

    static void tryq(Session s, String who, String q) {
        try { ResultSet rs = s.execute(q); System.out.println("CHECK " + who + " [" + q + "] -> OK rows=" + rs.getAvailableWithoutFetching()); }
        catch (Exception e) { System.out.println("CHECK " + who + " [" + q + "] -> " + msg(e)); }
    }

    static String big(int n) { StringBuilder b = new StringBuilder(n); while (b.length() < n) b.append('y'); return b.toString(); }

    // claim checks (code reading in the 3-b analysis), as each role over the native protocol
    static void authCheck(String host) throws Exception {
        for (String[] up : new String[][] { {null, null}, {"attacker", "wrong"} }) {
            try (Cluster c = cluster(host, 1, up[0], up[1]); Session s = c.connect()) { System.out.println("LOGIN " + up[0] + "/" + up[1] + " -> connected (unexpected)"); }
            catch (Exception e) { System.out.println("LOGIN " + up[0] + "/" + (up[1] == null ? null : "wrong") + " -> " + msg(e)); }
        }
        try (Cluster c = cluster(host, 1, "attacker", "atk-3b-B16"); Session s = c.connect()) {
            tryq(s, "attacker", "CREATE KEYSPACE x3b WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
            tryq(s, "attacker", "CREATE TABLE b16.x3b (pk int PRIMARY KEY)");
            tryq(s, "attacker", "ALTER TABLE b16.t WITH gc_grace_seconds = 0");
            tryq(s, "attacker", "DROP TABLE b16.t");
            tryq(s, "attacker", "SELECT * FROM vic.kv LIMIT 1");
            tryq(s, "attacker", "SELECT role FROM system_auth.roles");
            tryq(s, "attacker", "SELECT table_name, gc_grace_seconds FROM system_schema.tables WHERE keyspace_name = 'b16'");
            for (Row r : s.execute("SELECT table_name, gc_grace_seconds FROM system_schema.tables WHERE keyspace_name = 'b16'"))
                System.out.println("  schema b16." + r.getString(0) + " gc_grace_seconds=" + r.getInt(1));
            // clustering bound size: the 65,535-byte limit (db/ClusteringPrefix.java:278-287), on an unused partition of m
            // LOAD-try1 showed that the 65,536-B bound is accepted and then breaks the flush of b16.m (StatsMetadata,
            // AssertionError); so this check runs only with B16_BOUNDCHECK=1, never in the lifetime that makes the template.
            PreparedStatement d = s.prepare("DELETE FROM b16.m WHERE pk = 7 AND ck >= ? AND ck <= ?");
            if ("1".equals(System.getenv("B16_BOUNDCHECK"))) for (int n : new int[] {65534, 65535}) {   // bound = n + 1 bytes: 65,535 (at the limit), 65,536 (one over)
                try { s.execute(d.bind(big(n) + "a", big(n) + "b").setConsistencyLevel(ConsistencyLevel.ONE)); System.out.println("CHECK attacker range delete bound " + (n + 1) + " B -> OK"); }
                catch (Exception e) { System.out.println("CHECK attacker range delete bound " + (n + 1) + " B -> " + msg(e)); }
            }
        }
        try (Cluster c = cluster(host, 1, "tenant", "ten-3b-B16"); Session s = c.connect()) {
            tryq(s, "tenant", "SELECT * FROM b16.t WHERE pk = 0");
            tryq(s, "tenant", "SELECT * FROM vic.kv LIMIT 1");
        }
        try (Cluster c = cluster(host, 1, "reader", "rd-3b-B16"); Session s = c.connect()) {
            tryq(s, "reader", "DELETE FROM b16.t WHERE pk = 0 AND ck >= 'a' AND ck <= 'b'");
            tryq(s, "reader", "SELECT * FROM b16.m WHERE pk = 0");
        }
        System.out.println("authcheck done");
    }
}
