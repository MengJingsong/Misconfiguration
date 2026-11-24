// B17 client (pc72, loopback), adapted from U4Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE, 4 connections,
// read timeout 120 s, FallthroughRetryPolicy.
//   java B17Load schema <host>
//   java B17Load load   <host> <parts> <rows> <valueBytes> <conc>   values = new Random(pk*100003L+ck).nextBytes, <=5 retries
//   java B17Load verify <host>                                      per pk row count (paged); full paged read of pk 0 (fetch 64)
//   java B17Load seq    <host> <spec>                               spec items separated by ';':
//       one:Q:fetch:p1,p2,..     one query with these pks (fetch -1 = unpaged = setFetchSize(Integer.MAX_VALUE))
//       sweep:Q:k1,k2,..:reps:pauseMs   c = 1, for each k: reps queries (k-subset from Random(42+0)), pause between queries
//       idle:ms
//       run:Q:k:c1/secs1,c2/secs2,..    closed loop: c threads, thread t draws k-subsets from Random(42+t)
// Q: T = IN + ORDER BY ck LIMIT 10 (unpaged); M = IN + LIMIT 10 (fetch 5000); I = T + PER PARTITION LIMIT 10 (unpaged).
// Output (stdout): "Q {json}" per query; "S t,step_c,..." per second during run items; "ITEM ..." markers; "SUMMARY ...".
// 3-b confirm (pc75, 2026-11-23): credentials from env B17_USER / B17_PASS (PlainTextAuthProvider; unset = no credentials);
//   java B17Load admin-setup <host>   (superuser only) roles attacker / tenant / reader, admin schema b17.t and vic.kv, grants.
// Query paths, data and client options unchanged.
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B17Load {
    static Cluster cluster(String host, int conns) {
        String u = System.getenv("B17_USER"), p = System.getenv("B17_PASS");
        return cluster(host, conns, (u == null || u.isEmpty()) ? null : u, p);
    }
    static Cluster cluster(String host, int conns, String user, String pass) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4);
        if (user != null) b = b.withCredentials(user, pass);
        return b
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    static Session S;
    static final Map<String, PreparedStatement> PREP = new ConcurrentHashMap<>();
    static final Map<Integer, Random> RND = new ConcurrentHashMap<>();
    static final AtomicLong ok = new AtomicLong(), eRF = new AtomicLong(), eRT = new AtomicLong(), eInv = new AtomicLong(), eOth = new AtomicLong();
    static final AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
    static final AtomicReference<String> lastErr = new AtomicReference<>("");
    static final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
    static volatile boolean hostGone = false;

    static String cql(String q, int k) {
        StringBuilder in = new StringBuilder();
        for (int i = 0; i < k; i++) in.append(i == 0 ? "?" : ",?");
        String base = "SELECT * FROM b17.t WHERE pk IN (" + in + ")";
        switch (q) {
            case "T": return base + " ORDER BY ck LIMIT 10";
            case "M": return base + " LIMIT 10";
            case "I": return base + " ORDER BY ck PER PARTITION LIMIT 10 LIMIT 10";
        }
        throw new IllegalArgumentException(q);
    }

    static int defFetch(String q) { return q.equals("M") ? 5000 : Integer.MAX_VALUE; }

    static List<Integer> subset(int thread, int k) {
        Random r = RND.computeIfAbsent(thread, t -> new Random(42 + t));
        List<Integer> l = new ArrayList<>(); for (int i = 0; i < 16; i++) l.add(i);
        Collections.shuffle(l, r);
        return new ArrayList<>(l.subList(0, k));
    }

    static String esc(String s) { return String.valueOf(s).replace("\\", "/").replace("\"", "'").replace("\n", " "); }

    // one query; prints a Q line; returns true on success
    static boolean query(String q, List<Integer> pks, int fetch, int thread) {
        PreparedStatement ps = PREP.computeIfAbsent(q + pks.size(), x -> S.prepare(cql(q, pks.size())));
        BoundStatement bs = ps.bind(pks.toArray());
        bs.setFetchSize(fetch == -1 ? Integer.MAX_VALUE : fetch);
        long st = System.currentTimeMillis(), t0 = System.nanoTime();
        inflight.incrementAndGet();
        String err = null, msg = null; int rows = 0; long vb = 0; StringBuilder first = new StringBuilder();
        try {
            ResultSet rs = S.execute(bs);
            for (Row r : rs) {
                ByteBuffer v = r.getBytesUnsafe("v"); if (v != null) vb += v.remaining();
                if (rows < 10) first.append(rows == 0 ? "" : " ").append(r.getInt("pk")).append('/').append(r.getInt("ck"));
                rows++;
            }
        } catch (Exception e) {
            err = e.getClass().getSimpleName(); msg = e.getMessage();
            if (e instanceof NoHostAvailableException) hostGone = true;
        }
        long ms = (System.nanoTime() - t0) / 1000000;
        inflight.decrementAndGet();
        if (err == null) { ok.incrementAndGet(); rowsLast.set(rows); lat.add(ms); }
        else {
            if (err.equals("ReadFailureException")) eRF.incrementAndGet();
            else if (err.equals("ReadTimeoutException")) eRT.incrementAndGet();
            else if (err.equals("InvalidQueryException")) eInv.incrementAndGet();
            else eOth.incrementAndGet();
            lastErr.set(err + ": " + esc(msg).replace(',', ';'));
        }
        System.out.println("Q {\"start\":" + st + ",\"end\":" + System.currentTimeMillis() + ",\"ms\":" + ms + ",\"Q\":\"" + q
            + "\",\"k\":" + pks.size() + ",\"thread\":" + thread + ",\"fetch\":" + fetch + ",\"pks\":\"" + pks + "\",\"rows\":" + rows
            + ",\"first\":\"" + first + "\",\"vbytes\":" + vb + ",\"err\":" + (err == null ? "null" : "\"" + err + "\"")
            + ",\"msg\":" + (msg == null ? "null" : "\"" + esc(msg) + "\"") + "}");
        return err == null;
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("admin-setup")) { // 3-b confirm: superuser only creates roles, the admin schema and the grants
            String[][] roles = {{"attacker", "atk-3b-B17"}, {"tenant", "ten-3b-B17"}, {"reader", "rd-3b-B17"}};
            String[] st = {
                "CREATE KEYSPACE IF NOT EXISTS b17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                "CREATE TABLE IF NOT EXISTS b17.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))",
                "CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1}",
                "CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v text)",
                "GRANT SELECT ON TABLE b17.t TO attacker", "GRANT MODIFY ON TABLE b17.t TO attacker",
                "GRANT SELECT ON TABLE vic.kv TO tenant", "GRANT MODIFY ON TABLE vic.kv TO tenant",
                "GRANT SELECT ON TABLE b17.t TO reader" };
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (String[] r : roles) {
                    String q = "CREATE ROLE IF NOT EXISTS " + r[0] + " WITH PASSWORD = '" + r[1] + "' AND LOGIN = true AND SUPERUSER = false";
                    s.execute(q); System.out.println("ADMIN ok: " + q.replace(r[1], "***"));
                }
                for (String q : st) { s.execute(q); System.out.println("ADMIN ok: " + q); }
                for (String[] r : roles) {
                    for (Row row : s.execute("LIST ALL PERMISSIONS OF " + r[0]))
                        System.out.println("PERM " + r[0] + ": role=" + row.getString("role") + " resource=" + row.getString("resource") + " permission=" + row.getString("permission"));
                }
                for (Row row : s.execute("SELECT role, is_superuser, can_login FROM system_auth.roles"))
                    System.out.println("ROLE " + row.getString("role") + " superuser=" + row.getBool("is_superuser") + " login=" + row.getBool("can_login"));
                System.out.println("admin-setup ok");
            }
            return;
        }
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS b17.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("load")) {
            int parts = Integer.parseInt(a[2]), rows = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]), conc = Integer.parseInt(a[5]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO b17.t (pk, ck, v) VALUES (?, ?, ?)");
                ExecutorService ex = Executors.newFixedThreadPool(conc);
                AtomicLong retries = new AtomicLong(), failed = new AtomicLong(), done = new AtomicLong();
                List<Future<?>> fs = new ArrayList<>();
                for (int p = 0; p < parts; p++)
                    for (int k = 0; k < rows; k++) {
                        final int pk = p, ck = k;
                        fs.add(ex.submit(() -> {
                            byte[] b = new byte[size]; new Random(pk * 100003L + ck).nextBytes(b);
                            for (int t = 0; t <= 5; t++) {
                                try { s.execute(ps.bind(pk, ck, ByteBuffer.wrap(b))); done.incrementAndGet(); return; }
                                catch (Exception e) { if (t == 5) { failed.incrementAndGet(); System.out.println("load FAILED " + pk + "/" + ck + " " + e); } else { retries.incrementAndGet(); try { Thread.sleep(1000); } catch (InterruptedException ie) { return; } } }
                            }
                        }));
                    }
                for (Future<?> f : fs) f.get();
                ex.shutdown();
                System.out.println("load ok parts=" + parts + " rows=" + rows + " size=" + size + " done=" + done.get() + " retries=" + retries.get() + " failed=" + failed.get());
            }
            return;
        }
        if (a[0].equals("fill")) { // added 2026-11-18 14:05 EST: insert the rows the LOAD's retries could not write (same values)
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement q = s.prepare("SELECT ck FROM b17.t WHERE pk=?");
                PreparedStatement ps = s.prepare("INSERT INTO b17.t (pk, ck, v) VALUES (?, ?, ?)");
                int filled = 0;
                for (int pk = 0; pk < 16; pk++) {
                    BoundStatement bs = q.bind(pk); bs.setFetchSize(5000);
                    boolean[] have = new boolean[1024]; for (Row r : s.execute(bs)) have[r.getInt("ck")] = true;
                    for (int ck = 0; ck < 1024; ck++) if (!have[ck]) {
                        byte[] b = new byte[262144]; new Random(pk * 100003L + ck).nextBytes(b);
                        for (int t = 0; t <= 5; t++) { try { s.execute(ps.bind(pk, ck, ByteBuffer.wrap(b))); filled++; break; } catch (Exception e) { System.out.println("fill retry " + pk + "/" + ck + " " + e); Thread.sleep(2000); } }
                    }
                }
                System.out.println("fill ok filled=" + filled);
            }
            return;
        }
        if (a[0].equals("verify")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("SELECT ck FROM b17.t WHERE pk=?");
                long total = 0;
                for (int pk = 0; pk < 16; pk++) {
                    BoundStatement bs = ps.bind(pk); bs.setFetchSize(5000);
                    int n = 0; for (Row r : s.execute(bs)) n++;
                    total += n; System.out.println("verify pk=" + pk + " rows=" + n);
                }
                PreparedStatement pv = s.prepare("SELECT ck, v FROM b17.t WHERE pk=?");
                BoundStatement bs = pv.bind(0); bs.setFetchSize(64);
                long vb = 0; int n = 0, match = 0, checked = 0; long t0 = System.nanoTime();
                for (Row r : s.execute(bs)) {
                    ByteBuffer v = r.getBytesUnsafe("v"); vb += v.remaining(); n++;
                    int ck = r.getInt("ck");
                    if (ck == 0 || ck == 511 || ck == 1023) {
                        byte[] e = new byte[v.remaining()]; new Random(0 * 100003L + ck).nextBytes(e);
                        byte[] got = new byte[v.remaining()]; v.duplicate().get(got); checked++; if (Arrays.equals(e, got)) match++;
                    }
                }
                System.out.println("verify total_rows=" + total + " pk0_rows=" + n + " pk0_value_bytes=" + vb + " content_match=" + match + "/" + checked
                    + " ms=" + (System.nanoTime() - t0) / 1000000);
            }
            return;
        }
        // seq
        Cluster c = cluster(host, 4); S = c.connect();
        long tStart = System.currentTimeMillis();
        for (String item : a[2].split(";")) {
            String[] f = item.trim().split(":");
            System.out.println("ITEM " + System.currentTimeMillis() + " " + item.trim());
            switch (f[0]) {
                case "one": {
                    List<Integer> pks = new ArrayList<>(); for (String x : f[3].split(",")) pks.add(Integer.parseInt(x));
                    query(f[1], pks, Integer.parseInt(f[2]), 0); break;
                }
                case "sweep": {
                    int reps = Integer.parseInt(f[3]); long pause = Long.parseLong(f[4]); boolean firstQ = true;
                    for (String ks : f[2].split(",")) {
                        int k = Integer.parseInt(ks);
                        for (int i = 0; i < reps; i++) {
                            if (!firstQ) Thread.sleep(pause); firstQ = false;
                            query(f[1], subset(0, k), defFetch(f[1]), 0);
                            if (hostGone) { System.out.println("HOSTGONE"); finish(c, tStart); }
                        }
                    }
                    break;
                }
                case "idle": Thread.sleep(Long.parseLong(f[1])); break;
                case "run": runLoop(f[1], Integer.parseInt(f[2]), f[3].split(",")); break;
                default: System.out.println("bad item " + item);
            }
            if (hostGone) { System.out.println("HOSTGONE"); finish(c, tStart); }
        }
        finish(c, tStart);
    }

    static void finish(Cluster c, long tStart) {
        System.out.printf("SUMMARY secs=%.0f ok=%d err_readfail=%d err_readtimeout=%d err_invalid=%d err_other=%d inflight_left=%d%n",
            (System.currentTimeMillis() - tStart) / 1000.0, ok.get(), eRF.get(), eRT.get(), eInv.get(), eOth.get(), inflight.get());
        System.out.flush();
        c.closeAsync(); System.exit(hostGone ? 3 : 0);
    }

    static void runLoop(String q, int k, String[] steps) throws Exception {
        int maxc = 0; for (String s : steps) maxc = Math.max(maxc, Integer.parseInt(s.split("/")[0]));
        AtomicInteger target = new AtomicInteger(0); AtomicBoolean stop = new AtomicBoolean(false);
        List<Thread> ts = new ArrayList<>();
        for (int t = 0; t < maxc; t++) {
            final int id = t;
            Thread th = new Thread(() -> {
                while (!stop.get()) {
                    if (hostGone) return; // 2026-11-18 15:03 EST: stop a thread at once when the victim is gone (CAL-8G logged 28,177 NoHost errors)
                    if (id >= target.get()) { try { Thread.sleep(20); } catch (InterruptedException e) { return; } continue; }
                    query(q, subset(id, k), defFetch(q), id);
                }
            });
            th.setDaemon(true); th.start(); ts.add(th);
        }
        System.out.println("S t,step_c,inflight,ok,err_readfail,err_readtimeout,err_invalid,err_other,ok_s,p50ms,p99ms,maxms,rowsLast,lastErr");
        long lastOk = ok.get();
        for (String st : steps) {
            String[] kv = st.split("/"); int n = Integer.parseInt(kv[0]); long secs = Long.parseLong(kv[1]);
            target.set(n);
            for (long i = 0; i < secs; i++) {
                Thread.sleep(1000);
                long o = ok.get();
                List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
                Collections.sort(l);
                long p50 = l.isEmpty() ? -1 : l.get(l.size() / 2), p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))), mx = l.isEmpty() ? -1 : l.get(l.size() - 1);
                System.out.println("S " + System.currentTimeMillis() + "," + n + "," + inflight.get() + "," + o + "," + eRF.get() + "," + eRT.get() + ","
                    + eInv.get() + "," + eOth.get() + "," + (o - lastOk) + "," + p50 + "," + p99 + "," + mx + "," + rowsLast.get() + "," + lastErr.getAndSet(""));
                lastOk = o;
                if (hostGone) { stop.set(true); return; }
            }
        }
        stop.set(true); target.set(0);
        long w = System.currentTimeMillis() + 60000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
    }
}
