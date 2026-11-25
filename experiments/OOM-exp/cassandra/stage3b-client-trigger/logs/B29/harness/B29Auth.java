// 3-b confirm B29 (pc82, 2026-11-24): the stage-2 client B29Load (case harness) with credentials (-Db29.user / -Db29.pass),
// plus `cql` (run a statement file), `filler` (attacker's hint-backlog writes), `events` (driver host-state listener: the
// native protocol's STATUS_CHANGE / TOPOLOGY_CHANGE events as a client sees them), `waitup` (exit when a host is reported UP)
// and a `same` option for `run` (Q workers all query one partition once, concurrently).
// Java driver 3.12.1 (shaded), protocol v4, client-side timestamps, FallthroughRetryPolicy, whitelist = the given host only.
//   java B29Auth cql    <host> <file>                     each non-# line is one statement (QUORUM); prints OK/ERR + up to 40 rows
//   java B29Auth load   <host> <k0> <k1> <rows> <padBytes> <s> <CL>
//   java B29Auth f1     <host> <k0> <k1> <CL>             per k: DELETE partition, then UPDATE s='x' (later timestamp)
//   java B29Auth filler <host> <k0> <k1> <rows> <padBytes> <CL>   rows of random pad, no static (hint backlog)
//   java B29Auth stat   <host> <k> <CL> [trace]           SELECT s FROM b29.t WHERE k=?
//   java B29Auth one    <host> <k> <CL> [trace]           the attack query once
//   java B29Auth events <contactHost> <maxSecs> <stopFile>   prints every host up/down/add/remove the driver reports
//   java B29Auth waitup <contactHost> <targetHost> <maxSecs>  exits 0 when targetHost is reported UP
//   java B29Auth run    <host> <Q> <k0> <k1> <warmSecs> <maxSecs> [same]
//                         as B29Load run (QUORUM, prepared SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING);
//                         with `same`, the Q workers each run the query once on k0 at the same time
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B29Auth {
    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 1024).setMaxQueueSize(65536);
        Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting();
        String u = System.getProperty("b29.user");
        if (u != null) b = b.withCredentials(u, System.getProperty("b29.pass", ""));
        return b.build();
    }
    static final String Q = "SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING";
    static String err(Throwable e) { return e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '); }
    static String now() { return new java.text.SimpleDateFormat("HH:mm:ss.SSS").format(new Date()) + " (" + System.currentTimeMillis() + ")"; }

    static void async(Session s, Semaphore sem, AtomicLong er, Statement st) {
        sem.acquireUninterruptibly();
        Futures.addCallback(s.executeAsync(st), new FutureCallback<ResultSet>() {
            public void onSuccess(ResultSet x) { sem.release(); }
            public void onFailure(Throwable e) { er.incrementAndGet(); if (er.get() < 20) System.out.println("err " + err(e)); sem.release(); }
        }, MoreExecutors.directExecutor());
    }

    static void trace(ResultSet rs) {
        QueryTrace tr = rs.getExecutionInfo().getQueryTrace();
        if (tr == null) return;
        for (QueryTrace.Event ev : tr.getEvents())
            System.out.println("  trace " + ev.getSource() + " +" + ev.getSourceElapsedMicros() + "us [" + ev.getThreadName() + "] " + ev.getDescription());
    }

    static Host.StateListener listener(String tag, String target, CountDownLatch up) {
        return new Host.StateListener() {
            public void onAdd(Host h) { System.out.println(now() + " " + tag + " ADD " + h.getAddress()); }
            public void onUp(Host h) { System.out.println(now() + " " + tag + " UP " + h.getAddress()); if (up != null && h.getAddress().getHostAddress().equals(target)) up.countDown(); }
            public void onDown(Host h) { System.out.println(now() + " " + tag + " DOWN " + h.getAddress()); }
            public void onRemove(Host h) { System.out.println(now() + " " + tag + " REMOVE " + h.getAddress()); }
            public void onRegister(Cluster c) {}
            public void onUnregister(Cluster c) {}
        };
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("cql")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (String line : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(a[2]))) {
                    String st = line.trim(); if (st.isEmpty() || st.startsWith("#")) { if (!st.isEmpty()) System.out.println(st); continue; }
                    try {
                        ResultSet rs = s.execute(new SimpleStatement(st).setConsistencyLevel(ConsistencyLevel.QUORUM).setReadTimeoutMillis(60000));
                        int n = 0; StringBuilder sb = new StringBuilder();
                        for (Row r : rs) { if (n < 40) sb.append("\n   ROW ").append(r.toString()); n++; }
                        System.out.println("OK  " + st + "  -> rows=" + n + sb + (rs.getExecutionInfo().getWarnings().isEmpty() ? "" : " warnings=" + rs.getExecutionInfo().getWarnings()));
                    } catch (Exception e) {
                        System.out.println("ERR " + st + "  -> " + err(e));
                    }
                }
            } catch (Exception e) {
                System.out.println("ERR connect as " + System.getProperty("b29.user") + " -> " + err(e));
            }
            return;
        }
        if (a[0].equals("events") || a[0].equals("waitup")) {
            boolean wait = a[0].equals("waitup");
            String target = wait ? a[2] : null; long maxSecs = Long.parseLong(wait ? a[3] : a[2]);
            File stop = wait ? null : new File(a[3]);
            CountDownLatch up = new CountDownLatch(1);
            Cluster.Builder b = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
                .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(), Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
                .withReconnectionPolicy(new ConstantReconnectionPolicy(1000)).withoutJMXReporting();
            String u = System.getProperty("b29.user"); if (u != null) b = b.withCredentials(u, System.getProperty("b29.pass", ""));
            Cluster c = b.build();
            c.register(listener(a[0], target, up));
            c.init();
            System.out.println(now() + " " + a[0] + " connected via " + host + " as " + u + "; hosts:");
            for (Host h : c.getMetadata().getAllHosts()) {
                System.out.println("   " + h.getAddress() + " state=" + h.getState() + " isUp=" + h.isUp());
                if (wait && h.getAddress().getHostAddress().equals(target) && h.isUp()) up.countDown();
            }
            if (wait) {
                boolean ok = up.await(maxSecs, TimeUnit.SECONDS);
                System.out.println(now() + " waitup " + target + (ok ? " UP" : " TIMEOUT"));
                c.close(); System.exit(ok ? 0 : 1);
            }
            long t0 = System.currentTimeMillis();
            while (!stop.exists() && System.currentTimeMillis() - t0 < maxSecs * 1000) Thread.sleep(500);
            System.out.println(now() + " events end"); c.close(); System.exit(0);
        }
        if (a[0].equals("load") || a[0].equals("filler")) {
            boolean fill = a[0].equals("filler");
            int k0 = Integer.parseInt(a[2]), k1 = Integer.parseInt(a[3]), rows = Integer.parseInt(a[4]), size = Integer.parseInt(a[5]);
            String sv = fill ? null : a[6]; ConsistencyLevel cl = ConsistencyLevel.valueOf(fill ? a[6] : a[7]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement us = s.prepare("UPDATE b29.t SET s = ? WHERE k = ?"); us.setConsistencyLevel(cl);
                PreparedStatement ins = s.prepare("INSERT INTO b29.t (k, c, pad) VALUES (?, ?, ?)"); ins.setConsistencyLevel(cl);
                Semaphore sem = new Semaphore(8); AtomicLong er = new AtomicLong();
                long t0 = System.currentTimeMillis();
                for (int k = k0; k < k1; k++) {
                    if (!fill) s.execute(us.bind(sv, k));
                    Random r = new Random(29 + k);
                    for (int i = 0; i < rows; i++) {
                        byte[] bb = new byte[size]; r.nextBytes(bb);
                        async(s, sem, er, ins.bind(k, i, ByteBuffer.wrap(bb)));
                    }
                    System.out.println("loaded k=" + k + " t=" + (System.currentTimeMillis() - t0) / 1000 + "s errors=" + er.get());
                }
                sem.acquireUninterruptibly(8);
                System.out.println(a[0] + " ok k=" + k0 + ".." + (k1 - 1) + " rows=" + rows + " size=" + size + " s=" + sv + " CL=" + cl + " errors=" + er.get()
                                   + " secs=" + (System.currentTimeMillis() - t0) / 1000 + " as " + System.getProperty("b29.user"));
            }
            return;
        }
        if (a[0].equals("f1")) {
            int k0 = Integer.parseInt(a[2]), k1 = Integer.parseInt(a[3]); ConsistencyLevel cl = ConsistencyLevel.valueOf(a[4]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement del = s.prepare("DELETE FROM b29.t WHERE k = ?"); del.setConsistencyLevel(cl);
                PreparedStatement us = s.prepare("UPDATE b29.t SET s = 'x' WHERE k = ?"); us.setConsistencyLevel(cl);
                for (int k = k0; k < k1; k++) { s.execute(del.bind(k)); Thread.sleep(2); s.execute(us.bind(k)); }
                System.out.println(now() + " f1 ok k=" + k0 + ".." + (k1 - 1) + " CL=" + cl + " via " + host + " as " + System.getProperty("b29.user"));
            }
            return;
        }
        if (a[0].equals("stat") || a[0].equals("one")) {
            int k = Integer.parseInt(a[2]); ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]); boolean tr = a.length > 4;
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                String q = a[0].equals("stat") ? "SELECT s FROM b29.t WHERE k = ? LIMIT 1" : Q;
                Statement st = s.prepare(q).bind(k).setConsistencyLevel(cl).setReadTimeoutMillis(120000);
                if (tr) st.enableTracing();
                long t0 = System.nanoTime();
                try {
                    ResultSet rs = s.execute(st);
                    List<Row> all = rs.all();
                    StringBuilder sb = new StringBuilder();
                    for (Row r : all) sb.append(" s=").append(r.getString("s"));
                    System.out.println(a[0] + " k=" + k + " CL=" + cl + " via " + host + " rows=" + all.size() + sb + " ms=" + (System.nanoTime() - t0) / 1000000
                                       + " warnings=" + rs.getExecutionInfo().getWarnings());
                    if (tr) trace(rs);
                } catch (Exception e) { System.out.println(a[0] + " k=" + k + " CL=" + cl + " ERROR " + err(e)); }
            }
            return;
        }
        // run
        int nQ = Integer.parseInt(a[2]), k0 = Integer.parseInt(a[3]), k1 = Integer.parseInt(a[4]);
        int warm = Integer.parseInt(a[5]), maxSecs = Integer.parseInt(a[6]);
        boolean same = a.length > 7 && a[7].equals("same");
        Cluster c = cluster(host, 2); Session s = c.connect();
        System.out.println("# connected " + now() + " as " + System.getProperty("b29.user") + (same ? " mode=same k=" + k0 : ""));
        PreparedStatement ps = s.prepare(Q); ps.setConsistencyLevel(ConsistencyLevel.QUORUM);
        AtomicLong ok = new AtomicLong(), er = new AtomicLong(), ovl = new AtomicLong(), tmo = new AtomicLong(), rows1 = new AtomicLong(), rowsOther = new AtomicLong();
        AtomicInteger inflight = new AtomicInteger();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        PrintWriter qlog = new PrintWriter(new FileWriter("queries.csv", true), true);
        qlog.println("k,startMs,latMs,rows,error");
        AtomicBoolean stop = new AtomicBoolean(false);
        AtomicInteger next = new AtomicInteger(k0);
        AtomicReference<String> phase = new AtomicReference<>("warm");
        java.util.function.IntConsumer one = (k) -> {
            inflight.incrementAndGet(); long st = System.currentTimeMillis(); long t0 = System.nanoTime();
            String e1 = ""; int n = -1;
            try {
                ResultSet rs = s.execute(ps.bind(k));
                n = rs.all().size();
                ok.incrementAndGet(); if (n == 1) rows1.incrementAndGet(); else rowsOther.incrementAndGet();
            } catch (Exception e) {
                er.incrementAndGet(); e1 = err(e); lastErr.set(e1);
                if (e instanceof OverloadedException) ovl.incrementAndGet();
                if (e instanceof ReadTimeoutException || e instanceof OperationTimedOutException) tmo.incrementAndGet();
            }
            long l = (System.nanoTime() - t0) / 1000; lat.add(l); inflight.decrementAndGet();
            qlog.println(k + "," + st + "," + l / 1000 + "," + n + "," + e1);
        };
        Thread w0 = new Thread(() -> { int i = 0; while (phase.get().equals("warm") && !stop.get()) one.accept(1000 + (i++ % 10)); });
        w0.setDaemon(true); if (warm > 0) w0.start();
        List<Thread> workers = new ArrayList<>();
        System.out.println("t,phase,Q,inflight,ok,err,ok_s,p50ms,p99ms,rows1,rowsOther,overloaded,timeouts,lastErr");
        long tStart = System.currentTimeMillis(); long lastOk = 0;
        int secs = 0; boolean testStarted = false;
        while (true) {
            if (!testStarted && secs >= warm) {
                phase.set("test"); w0.join(30000); testStarted = true;
                System.out.println("# test step " + now());
                CountDownLatch go = new CountDownLatch(1);
                for (int i = 0; i < nQ; i++) {
                    Thread t = same ? new Thread(() -> { try { go.await(); } catch (InterruptedException ie) {} one.accept(k0); })
                                    : new Thread(() -> { int k; while (!stop.get() && (k = next.getAndIncrement()) < k1) one.accept(k); });
                    t.setDaemon(true); t.start(); workers.add(t);
                }
                go.countDown();
            }
            Thread.sleep(1000); secs++;
            long o = ok.get();
            List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
            Collections.sort(l);
            double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
            System.out.printf("%d,%s,%d,%d,%d,%d,%d,%.1f,%.1f,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), phase.get(), testStarted ? nQ : 1, inflight.get(), o, er.get(),
                              o - lastOk, p50, p99, rows1.get(), rowsOther.get(), ovl.get(), tmo.get(), lastErr.getAndSet(""));
            lastOk = o;
            if (testStarted) {
                boolean anyAlive = false; for (Thread t : workers) anyAlive |= t.isAlive();
                if (!anyAlive || secs >= warm + maxSecs) break;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d rows1=%d rowsOther=%d overloaded=%d timeouts=%d handedOut=%d inflight_left=%d%n",
                          (System.currentTimeMillis() - tStart) / 1000.0, ok.get(), er.get(), rows1.get(), rowsOther.get(), ovl.get(), tmo.get(),
                          same ? nQ : Math.min(next.get(), k1) - k0, inflight.get());
        qlog.close(); c.closeAsync(); System.exit(0);
    }
}
