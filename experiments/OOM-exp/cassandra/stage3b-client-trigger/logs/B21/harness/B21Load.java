// B21 3-b confirm client (pc72, loopback; 2026-11-23): stage-2 B21Load plus credentials (env B21_USER / B21_PASS ->
// PlainTextAuthProvider; no env = no credentials) and the modes admin-setup / authcheck / ddlcheck (below). The query paths
// (T, M, seq, load) are unchanged from stage 2. Stage-2 header follows.
// B21 client (ms0604, loopback), adapted from B17Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE, 4 connections,
// read timeout 120 s, FallthroughRetryPolicy.
//   java B21Load schema <host>
//   java B21Load load   <host> <rows> <bodyChars> <conc>   emb = 16 floats Random(id) in (0.1,1.0), bound as raw bytes
//                                                         (setBytesUnsafe); body = chars [a-z0-9] Random(1_000_003+id); <= 5 retries
//   java B21Load verify <host>                            paged count(*) and a paged id scan; checks a few bodies
//   java B21Load seq    <host> <spec>                     spec items separated by ';':
//       one:Q:limit:fetch:n:pauseMs     n sequential queries on thread 0
//       idle:ms
//       run:Q:limit:fetch:c1/secs1,c2/secs2,..   closed loop: c threads, thread t draws vectors/tokens from Random(42+t)
// Q: T = SELECT id, body FROM b21.docs ORDER BY emb ANN OF [16 floats] LIMIT <limit>   (non-prepared, literal vector)
//    M = SELECT id, body FROM b21.docs WHERE token(id) > ? LIMIT <limit>   (prepared; start token in the first 70 % of the ring;
//        the client iterates every page)
//    T on table big: TB (same as T against b21.big)
// Output (stdout): "Q {json}" per query; "S t,..." per second during run items; "ITEM ..." markers; "SUMMARY ...".
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B21Load {
    static Cluster cluster(String host, int conns) { return cluster(host, conns, System.getenv("B21_USER"), System.getenv("B21_PASS")); }
    static Cluster cluster(String host, int conns, String user, String pass) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        Cluster.Builder b = Cluster.builder();
        if (user != null && !user.isEmpty()) b = b.withCredentials(user, pass);
        return b.addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    static Session S;
    static PreparedStatement PM;
    static final Map<Integer, Random> RND = new ConcurrentHashMap<>();
    static final AtomicLong ok = new AtomicLong(), eRF = new AtomicLong(), eRT = new AtomicLong(), eInv = new AtomicLong(), eOth = new AtomicLong();
    static final AtomicLong rowsTot = new AtomicLong(), vbTot = new AtomicLong();
    static final AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
    static final AtomicReference<String> lastErr = new AtomicReference<>("");
    static final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
    static volatile boolean hostGone = false;
    static final long TOK_MIN = Long.MIN_VALUE;

    static float[] emb(long seed) {
        Random r = new Random(seed); float[] f = new float[16];
        for (int i = 0; i < 16; i++) f[i] = 0.1f + 0.9f * r.nextFloat();
        return f;
    }
    static ByteBuffer embBytes(float[] f) {
        ByteBuffer b = ByteBuffer.allocate(64); for (float x : f) b.putFloat(x); b.flip(); return b;
    }
    static String body(int id, int chars) {
        Random r = new Random(1_000_003L + id); char[] c = new char[chars];
        String al = "abcdefghijklmnopqrstuvwxyz0123456789";
        for (int i = 0; i < chars; i++) c[i] = al.charAt(r.nextInt(36));
        return new String(c);
    }
    static String esc(String s) { return String.valueOf(s).replace("\\", "/").replace("\"", "'").replace("\n", " "); }

    // one query; prints a Q line; returns true on success
    static boolean query(String q, int limit, int fetch, int thread) {
        Random r = RND.computeIfAbsent(thread, t -> new Random(42 + t));
        Statement st; String arg;
        if (q.equals("T") || q.equals("TB")) {
            float[] v = new float[16]; for (int i = 0; i < 16; i++) v[i] = 0.1f + 0.9f * r.nextFloat();
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 16; i++) sb.append(i == 0 ? "" : ", ").append(v[i]);
            String tab = q.equals("TB") ? "big" : "docs";
            st = new SimpleStatement("SELECT id, body FROM b21." + tab + " ORDER BY emb ANN OF [" + sb + "] LIMIT " + limit);
            arg = "v0=" + v[0];
        } else if (q.equals("M")) {
            // start token uniform in the first 70 % of the Murmur3 ring
            double u = r.nextDouble() * 0.7;
            long tok = (long) (TOK_MIN + u * 18446744073709551615.0);
            if (PM == null) synchronized (B21Load.class) { if (PM == null) PM = S.prepare("SELECT id, body FROM b21.docs WHERE token(id) > ? LIMIT " + limit); }
            st = PM.bind(tok); arg = "tok=" + tok;
        } else throw new IllegalArgumentException(q);
        st.setFetchSize(fetch);
        long stt = System.currentTimeMillis(), t0 = System.nanoTime();
        inflight.incrementAndGet();
        String err = null, msg = null, warn = ""; int rows = 0, pages = 0, warns = 0; long vb = 0; boolean more = false;
        try {
            ResultSet rs = S.execute(st);
            for (Row row : rs) {
                ByteBuffer b = row.getBytesUnsafe("body"); if (b != null) vb += b.remaining();
                rows++;
            }
            List<ExecutionInfo> ei = rs.getAllExecutionInfo(); pages = ei.size();
            for (ExecutionInfo e : ei) { List<String> w = e.getWarnings(); if (w != null) { warns += w.size(); if (!w.isEmpty() && warn.isEmpty()) warn = w.get(0); } }
            more = !rs.isFullyFetched();
        } catch (Exception e) {
            err = e.getClass().getSimpleName(); msg = e.getMessage();
            if (e instanceof NoHostAvailableException) hostGone = true;
        }
        long ms = (System.nanoTime() - t0) / 1000000;
        inflight.decrementAndGet();
        if (err == null) { ok.incrementAndGet(); rowsLast.set(rows); lat.add(ms); rowsTot.addAndGet(rows); vbTot.addAndGet(vb); }
        else {
            if (err.equals("ReadFailureException")) eRF.incrementAndGet();
            else if (err.equals("ReadTimeoutException") || err.equals("OperationTimedOutException")) eRT.incrementAndGet();
            else if (err.equals("InvalidQueryException")) eInv.incrementAndGet();
            else eOth.incrementAndGet();
            lastErr.set(err + ": " + esc(msg).replace(',', ';'));
        }
        System.out.println("Q {\"start\":" + stt + ",\"end\":" + System.currentTimeMillis() + ",\"ms\":" + ms + ",\"Q\":\"" + q
            + "\",\"limit\":" + limit + ",\"fetch\":" + fetch + ",\"thread\":" + thread + ",\"arg\":\"" + arg + "\",\"rows\":" + rows
            + ",\"pages\":" + pages + ",\"more\":" + more + ",\"vbytes\":" + vb + ",\"warns\":" + warns + ",\"warn\":\"" + esc(warn) + "\""
            + ",\"err\":" + (err == null ? "null" : "\"" + err + "\"")
            + ",\"msg\":" + (msg == null ? "null" : "\"" + esc(msg) + "\"") + "}");
        return err == null;
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("admin-setup")) { AuthCheck.adminSetup(host); return; }
        if (a[0].equals("authcheck")) { AuthCheck.check(host); return; }
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b21 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS b21.docs (id int PRIMARY KEY, emb vector<float, 16>, body text)");
                s.execute("CREATE INDEX IF NOT EXISTS docs_emb ON b21.docs(emb) USING 'sai'");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("schema-big")) { // IC-OVER table (optional)
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE TABLE IF NOT EXISTS b21.big (id int PRIMARY KEY, emb vector<float, 16>, body text)");
                s.execute("CREATE INDEX IF NOT EXISTS big_emb ON b21.big(emb) USING 'sai'");
                System.out.println("schema-big ok");
            }
            return;
        }
        if (a[0].equals("load") || a[0].equals("load-big")) {
            String tab = a[0].equals("load") ? "docs" : "big";
            int rows = Integer.parseInt(a[2]), chars = Integer.parseInt(a[3]), conc = Integer.parseInt(a[4]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO b21." + tab + " (id, emb, body) VALUES (?, ?, ?)");
                ExecutorService ex = Executors.newFixedThreadPool(conc);
                AtomicLong retries = new AtomicLong(), failed = new AtomicLong(), done = new AtomicLong();
                List<Future<?>> fs = new ArrayList<>();
                long t0 = System.nanoTime();
                for (int k = 0; k < rows; k++) {
                    final int id = k;
                    fs.add(ex.submit(() -> {
                        String b = body(id, chars); ByteBuffer e = embBytes(emb(id));
                        for (int t = 0; t <= 5; t++) {
                            try {
                                BoundStatement bs = ps.bind(); bs.setInt(0, id); bs.setBytesUnsafe(1, e.duplicate()); bs.setString(2, b);
                                s.execute(bs); long d = done.incrementAndGet();
                                if (d % 500 == 0) System.out.println("load progress " + d + " s=" + (System.nanoTime() - t0) / 1000000000);
                                return;
                            } catch (Exception ex2) {
                                if (t == 5) { failed.incrementAndGet(); System.out.println("load FAILED " + id + " " + ex2); }
                                else { retries.incrementAndGet(); System.out.println("load retry " + id + " " + ex2); try { Thread.sleep(1000); } catch (InterruptedException ie) { return; } }
                            }
                        }
                    }));
                }
                for (Future<?> f : fs) f.get();
                ex.shutdown();
                System.out.println("load ok table=" + tab + " rows=" + rows + " chars=" + chars + " done=" + done.get() + " retries=" + retries.get() + " failed=" + failed.get()
                    + " secs=" + (System.nanoTime() - t0) / 1000000000);
            }
            return;
        }
        if (a[0].equals("verify")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (Row r : s.execute("SELECT index_name, kind, options FROM system_schema.indexes WHERE keyspace_name = 'b21'"))
                    System.out.println("verify index " + r.getString(0) + " kind=" + r.getString(1) + " options=" + r.getMap(2, String.class, String.class));
                try {
                    for (Row r : s.execute("SELECT * FROM system_views.sai_column_indexes WHERE keyspace_name = 'b21' ALLOW FILTERING")) System.out.println("verify sai_column_indexes " + r);
                } catch (Exception e) { System.out.println("verify sai_column_indexes n/a: " + e); }
                Statement cs = new SimpleStatement("SELECT count(*) FROM b21.docs"); cs.setFetchSize(100);
                System.out.println("verify count(*)=" + s.execute(cs).one().getLong(0));
                Statement ids = new SimpleStatement("SELECT id, body FROM b21.docs"); ids.setFetchSize(100);
                int n = 0, checked = 0, match = 0; long vb = 0; BitSet seen = new BitSet();
                for (Row r : s.execute(ids)) {
                    int id = r.getInt("id"); seen.set(id); n++; String b = r.getString("body"); vb += b.length();
                    if (id % 997 == 0) { checked++; if (b.equals(body(id, b.length()))) match++; }
                }
                System.out.println("verify scan rows=" + n + " distinct=" + seen.cardinality() + " value_chars=" + vb + " body_match=" + match + "/" + checked);
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
                    int lim = Integer.parseInt(f[2]), fetch = Integer.parseInt(f[3]), n = Integer.parseInt(f[4]); long pause = Long.parseLong(f[5]);
                    for (int i = 0; i < n; i++) {
                        if (i > 0) Thread.sleep(pause);
                        query(f[1], lim, fetch, 0);
                        if (hostGone) { System.out.println("HOSTGONE"); finish(c, tStart); }
                    }
                    break;
                }
                case "idle": Thread.sleep(Long.parseLong(f[1])); break;
                case "run": runLoop(f[1], Integer.parseInt(f[2]), Integer.parseInt(f[3]), f[4].split(",")); break;
                default: System.out.println("bad item " + item);
            }
            if (hostGone) { System.out.println("HOSTGONE"); finish(c, tStart); }
        }
        finish(c, tStart);
    }

    static void finish(Cluster c, long tStart) {
        System.out.printf("SUMMARY secs=%.0f ok=%d err_readfail=%d err_timeout=%d err_invalid=%d err_other=%d inflight_left=%d rows=%d vbytes=%d%n",
            (System.currentTimeMillis() - tStart) / 1000.0, ok.get(), eRF.get(), eRT.get(), eInv.get(), eOth.get(), inflight.get(), rowsTot.get(), vbTot.get());
        System.out.flush();
        c.closeAsync(); System.exit(hostGone ? 3 : 0);
    }

    static void runLoop(String q, int limit, int fetch, String[] steps) throws Exception {
        int maxc = 0; for (String s : steps) maxc = Math.max(maxc, Integer.parseInt(s.split("/")[0]));
        AtomicInteger target = new AtomicInteger(0); AtomicBoolean stop = new AtomicBoolean(false);
        for (int t = 0; t < maxc; t++) {
            final int id = t;
            Thread th = new Thread(() -> {
                while (!stop.get()) {
                    if (hostGone) return;
                    if (id >= target.get()) { try { Thread.sleep(20); } catch (InterruptedException e) { return; } continue; }
                    query(q, limit, fetch, id);
                }
            });
            th.setDaemon(true); th.start();
        }
        System.out.println("S t,step_c,inflight,ok,err_readfail,err_timeout,err_invalid,err_other,ok_s,rows_s,vbytes_s,p50ms,p99ms,maxms,rowsLast,lastErr");
        long lastOk = ok.get(), lastRows = rowsTot.get(), lastVb = vbTot.get();
        for (String st : steps) {
            String[] kv = st.split("/"); int n = Integer.parseInt(kv[0]); long secs = Long.parseLong(kv[1]);
            target.set(n);
            for (long i = 0; i < secs; i++) {
                Thread.sleep(1000);
                long o = ok.get(), rw = rowsTot.get(), vb = vbTot.get();
                List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
                Collections.sort(l);
                long p50 = l.isEmpty() ? -1 : l.get(l.size() / 2), p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))), mx = l.isEmpty() ? -1 : l.get(l.size() - 1);
                System.out.println("S " + System.currentTimeMillis() + "," + n + "," + inflight.get() + "," + o + "," + eRF.get() + "," + eRT.get() + ","
                    + eInv.get() + "," + eOth.get() + "," + (o - lastOk) + "," + (rw - lastRows) + "," + (vb - lastVb) + "," + p50 + "," + p99 + "," + mx + "," + rowsLast.get() + "," + lastErr.getAndSet(""));
                lastOk = o; lastRows = rw; lastVb = vb;
                if (hostGone) { stop.set(true); return; }
            }
            System.out.println("STEPEND c=" + n + " ok=" + ok.get() + " rf=" + eRF.get() + " to=" + eRT.get() + " inv=" + eInv.get() + " oth=" + eOth.get());
        }
        stop.set(true); target.set(0);
        long w = System.currentTimeMillis() + 60000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
    }
}
