// 3-b confirm R24 (pc72, 2026-11-24): + credentials (-Dr24.user / -Dr24.pass; none = no credentials) and a `cql <host> <file>`
// subcommand (one statement per ';'-terminated block, prints each result or error). Otherwise stage 2's client.
// R24 load client (pc82, loopback), adapted from B22Load (OOM-exp B22 harness, itself from U4Load). Java driver 3.12.1 (shaded), protocol v4.
// Whitelist: node 1 (127.0.0.1) only; FallthroughRetryPolicy (no retry on another host). Changes for R24 (2026-11-24): keyspace r24,
// tables w2k/w4k/w8k/w12k (64 KiB pad) and s2k/s4k/s8k/s12k (2 KiB pad); explicit fetch size F (design: 128); every completed page
// is checked to hold F rows with c = 0..F-1 (or LIMIT rows); per-query outcome and latency log.
//   java R24Load schema <host>
//   java R24Load load   <host> <table> <rows> <padBytes>   k=0, c=0..rows-1, v='x', random pad (Random(7)), CL ALL, 8 in flight
//   java R24Load count  <host> <table>                     SELECT count(*) ... WHERE k=0 at CL ALL
//   java R24Load one    <host> <table> <CL> <fetch> <n> [limit]   n sequential first pages; one line each: rows, check, ms, warnings or error
//   java R24Load run    <host> <table> <CL> <fetch> <steps> <qlog>   closed loop, steps = "c:secs,...": c workers each issue the query,
//                                                           read the first page only, discard it and repeat. qlog: one line per query
//                                                           (start_ms,end_ms,ok|err,rows,check,error class).
// Query: SELECT k, c, v, pad FROM r24.<table> WHERE v = 'x' ALLOW FILTERING [LIMIT n] (range read, no partition-key restriction).
// run prints one CSV line per second:
//   t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,overloaded,timeouts,badpages,lastErr
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class R24Load {
    static final String[] TABLES = {"w2k", "w4k", "w8k", "w12k", "s2k", "s4k", "s8k", "s12k"};
    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 1024).setMaxQueueSize(65536);
        return creds(Cluster.builder()).addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting().build();
    }
    static Cluster.Builder creds(Cluster.Builder b) {
        String u = System.getProperty("r24.user");
        return u == null || u.isEmpty() ? b : b.withCredentials(u, System.getProperty("r24.pass", ""));
    }
    static String q(String table, int limit) { return "SELECT k, c, v, pad FROM r24." + table + " WHERE v = 'x'" + (limit > 0 ? " LIMIT " + limit : "") + " ALLOW FILTERING"; }
    static String err(Throwable e) { return e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '); }
    // returns {rows, padBytes, check(1 ok / 0 bad)}
    static long[] page(ResultSet rs, int expect) {
        int n = rs.getAvailableWithoutFetching(); long b = 0; boolean good = n == expect;
        for (int i = 0; i < n; i++) {
            Row r = rs.one(); ByteBuffer v = r.getBytesUnsafe("pad"); if (v != null) b += v.remaining();
            if (r.getInt("c") != i || r.getInt("k") != 0) good = false;
        }
        return new long[]{n, b, good ? 1 : 0};
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("cql")) {
            String all = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(a[2])));
            StringBuilder cur = new StringBuilder(); List<String> stmts = new ArrayList<>();
            for (String line : all.split("\n")) {
                String t = line.trim(); if (t.isEmpty() || t.startsWith("--")) continue;
                cur.append(t).append(' ');
                if (t.endsWith(";")) { stmts.add(cur.toString().trim()); cur.setLength(0); }
            }
            System.out.println("cql as role=" + System.getProperty("r24.user", "(none)") + " host=" + host);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (String q : stmts) {
                    try {
                        ResultSet rs = s.execute(new SimpleStatement(q).setReadTimeoutMillis(120000));
                        List<Row> rows = rs.all();
                        StringBuilder sb = new StringBuilder();
                        for (int i = 0; i < Math.min(rows.size(), 40); i++) sb.append("\n    ").append(rows.get(i).toString().replaceAll("java.nio.HeapByteBuffer\\[[^\\]]*\\]", "<blob>"));
                        System.out.println("OK   " + q + "  -> rows=" + rows.size() + " warnings=" + rs.getExecutionInfo().getWarnings() + sb);
                    } catch (Exception e) { System.out.println("ERR  " + q + "  -> " + err(e)); }
                }
                System.out.println("schema agreement=" + c.getMetadata().checkSchemaAgreement());
            } catch (Exception e) { System.out.println("CONNECT ERR " + err(e)); }
            return;
        }
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS r24 WITH replication = {'class':'SimpleStrategy','replication_factor':2}");
                for (String t : TABLES)
                    s.execute("CREATE TABLE IF NOT EXISTS r24." + t + " (k int, c int, v text, pad blob, PRIMARY KEY (k, c))");
                System.out.println("schema ok, agreement=" + c.getMetadata().checkSchemaAgreement());
            }
            return;
        }
        if (a[0].equals("load")) {
            String table = a[2]; int rows = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO r24." + table + " (k, c, v, pad) VALUES (0, ?, 'x', ?)");
                ps.setConsistencyLevel(ConsistencyLevel.ALL);
                Semaphore sem = new Semaphore(8); AtomicLong er = new AtomicLong(); Random r = new Random(7);
                for (int k = 0; k < rows; k++) {
                    byte[] b = new byte[size]; r.nextBytes(b);
                    sem.acquireUninterruptibly();
                    ResultSetFuture f = s.executeAsync(ps.bind(k, ByteBuffer.wrap(b)));
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet x) { sem.release(); }
                        public void onFailure(Throwable e) { er.incrementAndGet(); System.out.println("load err " + e); sem.release(); }
                    }, MoreExecutors.directExecutor());
                }
                sem.acquireUninterruptibly(8);
                System.out.println("load ok table=" + table + " rows=" + rows + " size=" + size + " errors=" + er.get());
            }
            return;
        }
        if (a[0].equals("count")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                Statement st = new SimpleStatement("SELECT count(*) FROM r24." + a[2] + " WHERE k = 0").setConsistencyLevel(ConsistencyLevel.ALL)
                    .setReadTimeoutMillis(120000);
                System.out.println("count " + a[2] + " CL ALL = " + s.execute(st).one().getLong(0));
            }
            return;
        }
        if (a[0].equals("one")) {
            String table = a[2]; ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]); int fetch = Integer.parseInt(a[4]), n = Integer.parseInt(a[5]);
            int limit = a.length > 6 ? Integer.parseInt(a[6]) : 0; int expect = limit > 0 ? Math.min(limit, fetch) : fetch;
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                System.out.println("one as role=" + System.getProperty("r24.user", "(none)"));
                for (int k = 0; k < n; k++) {
                    try {
                        Statement st = new SimpleStatement(q(table, limit)).setConsistencyLevel(cl).setFetchSize(fetch);
                        long t0 = System.nanoTime();
                        ResultSet rs = s.execute(st);
                        long ms = (System.nanoTime() - t0) / 1000000;
                        long[] p = page(rs, expect);
                        System.out.println("one table=" + table + " CL=" + cl + " fetch=" + fetch + " limit=" + limit + " OK rows=" + p[0] + " padBytes=" + p[1]
                                           + " check=" + (p[2] == 1 ? "ok" : "BAD") + " ms=" + ms + " morePages=" + !rs.isFullyFetched()
                                           + " warnings=" + rs.getExecutionInfo().getWarnings());
                    } catch (Exception e) {
                        System.out.println("one table=" + table + " CL=" + cl + " fetch=" + fetch + " limit=" + limit + " ERROR " + err(e));
                    }
                }
            } catch (Exception e) { System.out.println("one CONNECT ERROR as role=" + System.getProperty("r24.user", "(none)") + ": " + err(e)); }
            return;
        }
        // run
        String table = a[2]; ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]); int fetch = Integer.parseInt(a[4]); String[] steps = a[5].split(",");
        PrintWriter qlog = new PrintWriter(new BufferedWriter(new FileWriter(a[6])), false);
        qlog.println("start_ms,end_ms,outcome,rows,check,error");
        Cluster c = cluster(host, 2); Session s = c.connect();
        PreparedStatement ps = s.prepare(q(table, 0));
        ps.setConsistencyLevel(cl);
        AtomicLong ok = new AtomicLong(), er = new AtomicLong(), bytes = new AtomicLong(), ovl = new AtomicLong(), tmo = new AtomicLong(), bad = new AtomicLong(), nohost = new AtomicLong();
        AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        ConcurrentLinkedQueue<String> ql = new ConcurrentLinkedQueue<>();
        Semaphore sem = new Semaphore(0);
        AtomicInteger target = new AtomicInteger(0);
        AtomicBoolean stop = new AtomicBoolean(false);
        Thread gen = new Thread(() -> {
            while (!stop.get()) {
                try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                if (stop.get()) { sem.release(); return; }
                // R24 (2026-11-24, after DIAG-C): once the victim is gone, NoHostAvailable fails instantly; slow the loop and do not log those
                if (nohost.get() > 0) { try { Thread.sleep(200); } catch (InterruptedException e) { return; } }
                inflight.incrementAndGet();
                final long t0 = System.nanoTime(); final long w0 = System.currentTimeMillis();
                ResultSetFuture f = s.executeAsync(ps.bind().setFetchSize(fetch));
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        long[] p = page(rs, fetch);
                        if (p[2] == 0) bad.incrementAndGet();
                        rowsLast.set((int) p[0]); bytes.addAndGet(p[1]); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000);
                        ql.add(w0 + "," + System.currentTimeMillis() + ",ok," + p[0] + "," + (p[2] == 1 ? "ok" : "BAD") + ",");
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        if (e instanceof NoHostAvailableException) { nohost.incrementAndGet(); inflight.decrementAndGet(); sem.release(); return; }
                        er.incrementAndGet();
                        if (e instanceof OverloadedException) ovl.incrementAndGet();
                        if (e instanceof ReadTimeoutException || e instanceof OperationTimedOutException) tmo.incrementAndGet();
                        lastErr.set(err(e));
                        ql.add(w0 + "," + System.currentTimeMillis() + ",err,0,-," + err(e).replace(',', ';'));
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,overloaded,timeouts,badpages,lastErr");
        long tStart = System.currentTimeMillis(); long lastOk = 0, lastBytes = 0;
        for (String st : steps) {
            String[] kv = st.split(":"); int n = Integer.parseInt(kv[0]); long secs = Long.parseLong(kv[1]);
            int d = n - target.getAndSet(n);
            if (d > 0) sem.release(d); else if (d < 0) sem.acquireUninterruptibly(-d);
            for (long i = 0; i < secs; i++) {
                Thread.sleep(1000);
                long o = ok.get(), b = bytes.get();
                List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
                Collections.sort(l);
                double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
                System.out.printf("%d,%d,%d,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), n, inflight.get(), o, er.get(),
                                  o - lastOk, (b - lastBytes) / 1048576.0, p50, p99, rowsLast.get(), ovl.get(), tmo.get(), bad.get(), lastErr.getAndSet(""));
                String y; while ((y = ql.poll()) != null) qlog.println(y); qlog.flush();
                lastOk = o; lastBytes = b;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        String y; while ((y = ql.poll()) != null) qlog.println(y); qlog.close();
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d overloaded=%d timeouts=%d badpages=%d bytesMB=%.0f inflight_left=%d nohost=%d%n", (System.currentTimeMillis() - tStart) / 1000.0,
                          ok.get(), er.get(), ovl.get(), tmo.get(), bad.get(), bytes.get() / 1048576.0, inflight.get(), nohost.get());
        c.closeAsync(); System.exit(0);
    }
}
