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
    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
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
}
