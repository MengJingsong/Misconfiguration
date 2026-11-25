// B29 load client (pc72, loopback), adapted from B22Load (OOM-exp B22 harness). Java driver 3.12.1 (shaded), protocol v4,
// client-side timestamps (driver default monotonic generator), FallthroughRetryPolicy, whitelist = the given host only.
//   java B29Load schema <host>
//   java B29Load load   <host> <k0> <k1> <rows> <padBytes> <s> <CL>   per k in [k0,k1): UPDATE s, then rows c=0..rows-1 with
//                                                                     a random pad (Random(29+k)); 8 in flight
//   java B29Load f1     <host> <k0> <k1> <CL>                          per k: DELETE partition, then UPDATE s='x' (later timestamp)
//   java B29Load stat   <host> <k> <CL> [trace]                        SELECT s FROM b29.t WHERE k=? (optionally traced: sources)
//   java B29Load one    <host> <k> <CL> [trace]                        the test query once; rows, latency, trace events
//   java B29Load run    <host> <Q> <k0> <k1> <warmSecs> <maxSecs>     warm-up: 1 worker round-robin over k=1000..1009 for warmSecs;
//                         then Q workers take the next k from a shared counter over [k0,k1) (each k once) in a closed loop until
//                         the counter is exhausted or maxSecs. Query (prepared, QUORUM):
//                         SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING
// run prints one CSV line per second (stdout):
//   t,phase,Q,inflight,ok,err,ok_s,p50ms,p99ms,rows1,rowsOther,overloaded,timeouts,lastErr
// and one line per finished query to queries.csv in the cwd: k,startMs,latMs,rows,error
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B29Load {
    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 1024).setMaxQueueSize(65536);
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting().build();
    }
    static final String Q = "SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING";
    static String err(Throwable e) { return e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '); }

    static void async(Session s, Semaphore sem, AtomicLong er, Statement st) {
        sem.acquireUninterruptibly();
        Futures.addCallback(s.executeAsync(st), new FutureCallback<ResultSet>() {
            public void onSuccess(ResultSet x) { sem.release(); }
            public void onFailure(Throwable e) { er.incrementAndGet(); System.out.println("err " + err(e)); sem.release(); }
        }, MoreExecutors.directExecutor());
    }

    static void trace(ResultSet rs) {
        QueryTrace tr = rs.getExecutionInfo().getQueryTrace();
        if (tr == null) return;
        for (QueryTrace.Event ev : tr.getEvents())
            System.out.println("  trace " + ev.getSource() + " +" + ev.getSourceElapsedMicros() + "us [" + ev.getThreadName() + "] " + ev.getDescription());
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b29 WITH replication = {'class':'SimpleStrategy','replication_factor':2}");
                s.execute("CREATE TABLE IF NOT EXISTS b29.t (k int, c int, s text STATIC, pad blob, PRIMARY KEY (k, c))");
                System.out.println("schema ok, agreement=" + c.getMetadata().checkSchemaAgreement());
            }
            return;
        }
        if (a[0].equals("load")) {
            int k0 = Integer.parseInt(a[2]), k1 = Integer.parseInt(a[3]), rows = Integer.parseInt(a[4]), size = Integer.parseInt(a[5]);
            String sv = a[6]; ConsistencyLevel cl = ConsistencyLevel.valueOf(a[7]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement us = s.prepare("UPDATE b29.t SET s = ? WHERE k = ?"); us.setConsistencyLevel(cl);
                PreparedStatement ins = s.prepare("INSERT INTO b29.t (k, c, pad) VALUES (?, ?, ?)"); ins.setConsistencyLevel(cl);
                Semaphore sem = new Semaphore(8); AtomicLong er = new AtomicLong();
                long t0 = System.currentTimeMillis();
                for (int k = k0; k < k1; k++) {
                    s.execute(us.bind(sv, k));
                    Random r = new Random(29 + k);
                    for (int i = 0; i < rows; i++) {
                        byte[] b = new byte[size]; r.nextBytes(b);
                        async(s, sem, er, ins.bind(k, i, ByteBuffer.wrap(b)));
                    }
                    if ((k - k0) % 8 == 7) System.out.println("loaded k<=" + k + " t=" + (System.currentTimeMillis() - t0) / 1000 + "s errors=" + er.get());
                }
                sem.acquireUninterruptibly(8);
                System.out.println("load ok k=" + k0 + ".." + (k1 - 1) + " rows=" + rows + " size=" + size + " s=" + sv + " CL=" + cl + " errors=" + er.get()
                                   + " secs=" + (System.currentTimeMillis() - t0) / 1000);
            }
            return;
        }
        if (a[0].equals("f1")) {
            int k0 = Integer.parseInt(a[2]), k1 = Integer.parseInt(a[3]); ConsistencyLevel cl = ConsistencyLevel.valueOf(a[4]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement del = s.prepare("DELETE FROM b29.t WHERE k = ?"); del.setConsistencyLevel(cl);
                PreparedStatement us = s.prepare("UPDATE b29.t SET s = 'x' WHERE k = ?"); us.setConsistencyLevel(cl);
                for (int k = k0; k < k1; k++) { s.execute(del.bind(k)); Thread.sleep(2); s.execute(us.bind(k)); }
                System.out.println("f1 ok k=" + k0 + ".." + (k1 - 1) + " CL=" + cl);
            }
            return;
        }
        if (a[0].equals("stat") || a[0].equals("one")) {
            int k = Integer.parseInt(a[2]); ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]); boolean tr = a.length > 4;
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                String q = a[0].equals("stat") ? "SELECT s FROM b29.t WHERE k = ?" : Q;
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
        Cluster c = cluster(host, 2); Session s = c.connect();
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
        // one query, synchronous, on the calling worker thread
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
        w0.setDaemon(true); w0.start();
        List<Thread> workers = new ArrayList<>();
        System.out.println("t,phase,Q,inflight,ok,err,ok_s,p50ms,p99ms,rows1,rowsOther,overloaded,timeouts,lastErr");
        long tStart = System.currentTimeMillis(); long lastOk = 0;
        int secs = 0; boolean testStarted = false;
        while (true) {
            Thread.sleep(1000); secs++;
            if (!testStarted && secs >= warm) {
                phase.set("test"); w0.join(30000); testStarted = true;
                for (int i = 0; i < nQ; i++) {
                    Thread t = new Thread(() -> { int k; while (!stop.get() && (k = next.getAndIncrement()) < k1) one.accept(k); });
                    t.setDaemon(true); t.start(); workers.add(t);
                }
            }
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
                          Math.min(next.get(), k1) - k0, inflight.get());
        qlog.close(); c.closeAsync(); System.exit(0);
    }
}
