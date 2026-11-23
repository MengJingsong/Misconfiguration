// B22 load client (pc82, loopback), adapted from U4Load (OOM-exp U4 harness). Java driver 3.12.1 (shaded), protocol v4.
// Whitelist: node 1 (127.0.0.1) only; FallthroughRetryPolicy (no retry on another host); fetch size = driver default (5,000).
//   java B22Load schema <host>
//   java B22Load load   <host> <table> <rows> <padBytes>   k=0, c=0..rows-1, v='x', random pad (Random(7)), CL ALL, 8 in flight
//   java B22Load count  <host> <table>                     SELECT count(*) ... WHERE k=0 at CL ALL
//   java B22Load one    <host> <table> <CL>                one filtering query (first page); rows, pad bytes, warnings or the error
//   java B22Load run    <host> <table> <CL> <steps>        closed loop, steps = "c:secs,...": c workers each issue the query,
//                                                           read the first page only, discard it and repeat.
// Query: SELECT k, c, v, pad FROM b22.<table> WHERE v = 'x' ALLOW FILTERING (range read, no partition-key restriction).
// run prints one CSV line per second:
//   t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,overloaded,timeouts,lastErr
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B22Load {
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
    static String q(String table) { return "SELECT k, c, v, pad FROM b22." + table + " WHERE v = 'x' ALLOW FILTERING"; }
    static String err(Throwable e) { return e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '); }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS b22 WITH replication = {'class':'SimpleStrategy','replication_factor':2}");
                for (String t : new String[]{"wide", "small"})
                    s.execute("CREATE TABLE IF NOT EXISTS b22." + t + " (k int, c int, v text, pad blob, PRIMARY KEY (k, c))");
                System.out.println("schema ok, agreement=" + c.getMetadata().checkSchemaAgreement());
            }
            return;
        }
        if (a[0].equals("load")) {
            String table = a[2]; int rows = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO b22." + table + " (k, c, v, pad) VALUES (0, ?, 'x', ?)");
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
                Statement st = new SimpleStatement("SELECT count(*) FROM b22." + a[2] + " WHERE k = 0").setConsistencyLevel(ConsistencyLevel.ALL)
                    .setReadTimeoutMillis(120000);
                System.out.println("count " + a[2] + " CL ALL = " + s.execute(st).one().getLong(0));
            }
            return;
        }
        if (a[0].equals("one")) {
            String table = a[2]; ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                try {
                    Statement st = new SimpleStatement(q(table)).setConsistencyLevel(cl);
                    long t0 = System.nanoTime();
                    ResultSet rs = s.execute(st);
                    int n = rs.getAvailableWithoutFetching(); long bytes = 0;
                    for (int i = 0; i < n; i++) { ByteBuffer v = rs.one().getBytesUnsafe("pad"); if (v != null) bytes += v.remaining(); }
                    System.out.println("one table=" + table + " CL=" + cl + " fetch=" + st.getFetchSize() + "(0=default " + c.getConfiguration().getQueryOptions().getFetchSize()
                                       + ") OK firstPageRows=" + n + " padBytes=" + bytes + " ms=" + (System.nanoTime() - t0) / 1000000
                                       + " morePages=" + !rs.isFullyFetched() + " warnings=" + rs.getExecutionInfo().getWarnings());
                } catch (Exception e) {
                    System.out.println("one table=" + table + " CL=" + cl + " ERROR " + err(e));
                }
            }
            return;
        }
        // run
        String table = a[2]; ConsistencyLevel cl = ConsistencyLevel.valueOf(a[3]); String[] steps = a[4].split(",");
        Cluster c = cluster(host, 2); Session s = c.connect();
        PreparedStatement ps = s.prepare(q(table));
        ps.setConsistencyLevel(cl);
        AtomicLong ok = new AtomicLong(), er = new AtomicLong(), bytes = new AtomicLong(), ovl = new AtomicLong(), tmo = new AtomicLong();
        AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        Semaphore sem = new Semaphore(0);
        AtomicInteger target = new AtomicInteger(0);
        AtomicBoolean stop = new AtomicBoolean(false);
        Thread gen = new Thread(() -> {
            while (!stop.get()) {
                try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                if (stop.get()) { sem.release(); return; }
                inflight.incrementAndGet();
                final long t0 = System.nanoTime();
                ResultSetFuture f = s.executeAsync(ps.bind());
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        long b = 0; int n = rs.getAvailableWithoutFetching();
                        for (int i = 0; i < n; i++) { ByteBuffer v = rs.one().getBytesUnsafe("pad"); if (v != null) b += v.remaining(); }
                        rowsLast.set(n); bytes.addAndGet(b); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000);
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        er.incrementAndGet();
                        if (e instanceof OverloadedException) ovl.incrementAndGet();
                        if (e instanceof ReadTimeoutException || e instanceof OperationTimedOutException) tmo.incrementAndGet();
                        lastErr.set(err(e));
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,overloaded,timeouts,lastErr");
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
                System.out.printf("%d,%d,%d,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%s%n", System.currentTimeMillis(), n, inflight.get(), o, er.get(),
                                  o - lastOk, (b - lastBytes) / 1048576.0, p50, p99, rowsLast.get(), ovl.get(), tmo.get(), lastErr.getAndSet(""));
                lastOk = o; lastBytes = b;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d overloaded=%d timeouts=%d bytesMB=%.0f inflight_left=%d%n", (System.currentTimeMillis() - tStart) / 1000.0,
                          ok.get(), er.get(), ovl.get(), tmo.get(), bytes.get() / 1048576.0, inflight.get());
        c.closeAsync(); System.exit(0);
    }
}
