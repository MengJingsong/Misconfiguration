// 3-b confirm (pc91, 2026-11-24): credentials from -Du4.user / -Du4.pass (PasswordAuthenticator), plus
//   java U4Load cql <host> <file>   run each ';'-terminated statement of <file> as that role; print rows or the error.
// Otherwise unchanged from stage 2.
// U4 load client (pc75, loopback), adapted from C2Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE.
//   java U4Load schema <host>
//   java U4Load load   <host> <parts> <rows> <valueBytes> <pk0>     insert parts x rows rows of random blobs (Random(pk0)), 32 async in flight
//   java U4Load one    <host> <pk> <fetch>                         one read (first page); prints rows, value bytes, or the error
//   java U4Load run    <host> <conns> <steps> <parts> <fetch>      closed-loop reads, steps = "c:secs,c:secs,..."
// run: prepared SELECT * FROM u4.t WHERE pk=? (random pk in [0,parts), seed 42), fetch size <fetch>, first page only,
// c requests in flight over <conns> connections. One CSV line per second:
//   t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,lastErr      values counted and dropped.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U4Load {
    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        Cluster.Builder bld = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(120000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting();
        String u = System.getProperty("u4.user");
        Cluster.Builder b = bld; if (u != null) b = b.withCredentials(u, System.getProperty("u4.pass", ""));
        return b.build();
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("cql")) {
            String all = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(a[2])));
            System.out.println("== role " + System.getProperty("u4.user"));
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (String st : all.split(";")) {
                    st = st.replaceAll("(?m)^--.*$", "").trim(); if (st.isEmpty()) continue;
                    try {
                        ResultSet rs = s.execute(new SimpleStatement(st).setFetchSize(100));
                        int n = 0; StringBuilder sb = new StringBuilder();
                        for (Row r : rs) { if (n < 40) sb.append("\n    ").append(r.toString().replace("\n", " ")); n++; if (n >= 200) break; }
                        System.out.println("OK   " + st.replace('\n', ' ') + "  rows=" + n + sb);
                    } catch (Exception e) {
                        System.out.println("ERR  " + st.replace('\n', ' ') + "  -> " + e.getClass().getSimpleName() + ": " + e.getMessage());
                    }
                }
            } catch (Exception e) { System.out.println("CONNECT-ERR " + e.getClass().getSimpleName() + ": " + e.getMessage()); System.exit(3); }
            return;
        }
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u4 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS u4.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("load")) {
            int parts = Integer.parseInt(a[2]), rows = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]), pk0 = Integer.parseInt(a[5]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO u4.t (pk, ck, v) VALUES (?, ?, ?)");
                ps.setConsistencyLevel(ConsistencyLevel.ONE);
                Semaphore sem = new Semaphore(32); AtomicLong err = new AtomicLong(); Random r = new Random(pk0);
                for (int p = pk0; p < pk0 + parts; p++)
                    for (int k = 0; k < rows; k++) {
                        byte[] b = new byte[size]; r.nextBytes(b);
                        sem.acquireUninterruptibly();
                        ResultSetFuture f = s.executeAsync(ps.bind(p, k, ByteBuffer.wrap(b)));
                        Futures.addCallback(f, new FutureCallback<ResultSet>() {
                            public void onSuccess(ResultSet x) { sem.release(); }
                            public void onFailure(Throwable e) { err.incrementAndGet(); System.out.println("load err " + e); sem.release(); }
                        }, MoreExecutors.directExecutor());
                    }
                sem.acquireUninterruptibly(32);
                System.out.println("load ok parts=" + parts + " rows=" + rows + " size=" + size + " pk0=" + pk0 + " errors=" + err.get());
            }
            return;
        }
        if (a[0].equals("one")) {
            int pk = Integer.parseInt(a[2]); int fetch = Integer.parseInt(a[3]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                try {
                    Statement st = new SimpleStatement("SELECT * FROM u4.t WHERE pk=" + pk).setFetchSize(fetch);
                    long t0 = System.nanoTime();
                    ResultSet rs = s.execute(st);
                    int n = rs.getAvailableWithoutFetching(); long bytes = 0;
                    for (int i = 0; i < n; i++) { ByteBuffer v = rs.one().getBytesUnsafe("v"); if (v != null) bytes += v.remaining(); }
                    System.out.println("one pk=" + pk + " fetch=" + fetch + " OK firstPageRows=" + n + " valueBytes=" + bytes
                                       + " ms=" + (System.nanoTime() - t0) / 1000000 + " morePages=" + !rs.isFullyFetched()
                                       + " warnings=" + rs.getExecutionInfo().getWarnings());
                } catch (Exception e) {
                    System.out.println("one pk=" + pk + " fetch=" + fetch + " ERROR " + e.getClass().getSimpleName() + ": " + e.getMessage());
                }
            }
            return;
        }
        // run
        int conns = Integer.parseInt(a[2]); String[] steps = a[3].split(","); int parts = Integer.parseInt(a[4]);
        final int fetch = Integer.parseInt(a[5]);
        Cluster c = cluster(host, conns); Session s = c.connect();
        PreparedStatement ps = s.prepare("SELECT * FROM u4.t WHERE pk=?");
        ps.setConsistencyLevel(ConsistencyLevel.ONE);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), bytes = new AtomicLong();
        AtomicInteger inflight = new AtomicInteger(), rowsLast = new AtomicInteger(-1);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        Semaphore sem = new Semaphore(0);
        AtomicInteger target = new AtomicInteger(0);
        AtomicBoolean stop = new AtomicBoolean(false);
        Thread gen = new Thread(() -> {
            Random r = new Random(42);
            while (!stop.get()) {
                try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                if (stop.get()) { sem.release(); return; }
                inflight.incrementAndGet();
                final long t0 = System.nanoTime();
                BoundStatement bs = ps.bind(r.nextInt(parts)); bs.setFetchSize(fetch);
                ResultSetFuture f = s.executeAsync(bs);
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        long b = 0; int n = rs.getAvailableWithoutFetching();
                        for (int i = 0; i < n; i++) { ByteBuffer v = rs.one().getBytesUnsafe("v"); if (v != null) b += v.remaining(); }
                        rowsLast.set(n); bytes.addAndGet(b); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000);
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        err.incrementAndGet(); lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '));
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,lastErr");
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
                System.out.printf("%d,%d,%d,%d,%d,%d,%.1f,%.1f,%.1f,%d,%s%n", System.currentTimeMillis(), n, inflight.get(), o, err.get(),
                                  o - lastOk, (b - lastBytes) / 1048576.0, p50, p99, rowsLast.get(), lastErr.getAndSet(""));
                lastOk = o; lastBytes = b;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d bytesMB=%.0f inflight_left=%d%n", (System.currentTimeMillis() - tStart) / 1000.0,
                          ok.get(), err.get(), bytes.get() / 1048576.0, inflight.get());
        c.closeAsync(); System.exit(0);
    }
}
