// U10 load client (pc82, loopback), adapted from U4Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE,
// FallthroughRetryPolicy, socket read timeout 120 s. fetch "off" = setFetchSize(Integer.MAX_VALUE) (the driver then
// sends no PAGE_SIZE, server sees -1); a number = that fetch size.
//   java U10Load schema <host>
//   java U10Load load   <host> <parts> <rows> <valueBytes>          pk 0..parts-1, ck 0..rows-1, Random(1000+pk) bytes; 64 async, 5 retries
//   java U10Load verify <host> <parts>                              paged (5000) SELECT ck count per pk; v length at ck=0
//   java U10Load one    <host> <pk> <n> <fetch> <kind>              kind agg|sel|grs; prints result, rows, latency, paging state, error
//   java U10Load cal    <host> <fetch> <reps> <n1,n2,...>           sequential agg queries (pk = i mod 8), one line each
//   java U10Load run    <host> <conns> <steps> <fetch> <kind>       closed loop, steps "c:n:secs,..."; read i uses pk = i mod 8
// kinds: agg = SELECT count(v) FROM u10.t WHERE pk=? AND ck<?   sel = SELECT ck FROM u10.t WHERE pk=? AND ck<?
//        grs = SELECT pk, ck, v FROM u10.t WHERE pk=? AND ck<? GROUP BY pk, ck
// run CSV (one line per second): t,step_c,step_n,inflight,done,ok_s,correct_s,err_rt_s,err_rf_s,err_other_s,mean_ms,max_ms,lastErr
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class U10Load {
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

    static int fetch(String f) { return f.equals("off") ? Integer.MAX_VALUE : Integer.parseInt(f); }

    static String q(String kind) {
        switch (kind) {
            case "agg": return "SELECT count(v) FROM u10.t WHERE pk = ? AND ck < ?";
            case "sel": return "SELECT ck FROM u10.t WHERE pk = ? AND ck < ?";
            case "grs": return "SELECT pk, ck, v FROM u10.t WHERE pk = ? AND ck < ? GROUP BY pk, ck";
        }
        throw new IllegalArgumentException(kind);
    }

    static String err(Throwable e) {
        return e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' ');
    }

    static int errClass(Throwable e) {
        if (e instanceof ReadTimeoutException) return 0;
        if (e instanceof ReadFailureException) return 1;
        return 2;
    }

    // result of one agg/sel/grs ResultSet (first page only): {value, rowsInFirstPage}
    static long[] res(ResultSet rs, String kind) {
        int n = rs.getAvailableWithoutFetching();
        if (kind.equals("agg")) { Row r = rs.one(); return new long[]{r == null ? -1 : r.getLong(0), n}; }
        long rows = 0; for (int i = 0; i < n; i++) { rs.one(); rows++; }
        return new long[]{rows, n};
    }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS u10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS u10.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("load")) {
            int parts = Integer.parseInt(a[2]), rows = Integer.parseInt(a[3]), size = Integer.parseInt(a[4]);
            try (Cluster c = cluster(host, 4); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO u10.t (pk, ck, v) VALUES (?, ?, ?)");
                ps.setConsistencyLevel(ConsistencyLevel.ONE);
                Semaphore sem = new Semaphore(64); AtomicLong fails = new AtomicLong(), retries = new AtomicLong(), done = new AtomicLong();
                long t0 = System.currentTimeMillis();
                for (int p = 0; p < parts; p++) {
                    Random r = new Random(1000 + p);
                    for (int k = 0; k < rows; k++) {
                        byte[] b = new byte[size]; r.nextBytes(b);
                        sem.acquireUninterruptibly();
                        final int pp = p, kk = k;
                        insert(s, ps, pp, kk, b, 0, sem, fails, retries, done);
                        if ((k & 8191) == 0) System.out.println("load progress pk=" + p + " ck=" + k + " done=" + done.get() + " retries=" + retries.get()
                                                                   + " fails=" + fails.get() + " secs=" + (System.currentTimeMillis() - t0) / 1000);
                    }
                }
                sem.acquireUninterruptibly(64);
                System.out.println("load ok parts=" + parts + " rows=" + rows + " size=" + size + " done=" + done.get() + " retries=" + retries.get()
                                   + " fails=" + fails.get() + " secs=" + (System.currentTimeMillis() - t0) / 1000);
            }
            return;
        }
        if (a[0].equals("reload")) {   // reload <host> <rows> <valueBytes> <pk:ck,pk:ck,...>  same bytes as load (Random(1000+pk) sequence), sync inserts
            int rows = Integer.parseInt(a[2]), size = Integer.parseInt(a[3]);
            Map<Integer, Set<Integer>> want = new TreeMap<>();
            for (String x : a[4].split(",")) { if (x.isEmpty()) continue; String[] pc = x.split(":"); want.computeIfAbsent(Integer.parseInt(pc[0]), k -> new HashSet<>()).add(Integer.parseInt(pc[1])); }
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO u10.t (pk, ck, v) VALUES (?, ?, ?)");
                int n = 0;
                for (Map.Entry<Integer, Set<Integer>> e : want.entrySet()) {
                    Random r = new Random(1000 + e.getKey());
                    for (int k = 0; k < rows; k++) {
                        byte[] b = new byte[size]; r.nextBytes(b);
                        if (e.getValue().contains(k)) { s.execute(ps.bind(e.getKey(), k, ByteBuffer.wrap(b))); n++; }
                    }
                }
                System.out.println("reload ok rows=" + n);
            }
            return;
        }
        if (a[0].equals("verify")) {
            int parts = Integer.parseInt(a[2]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                for (int p = 0; p < parts; p++) {
                    ResultSet rs = s.execute(new SimpleStatement("SELECT ck FROM u10.t WHERE pk = " + p).setFetchSize(5000));
                    long n = 0, mx = -1; for (Row r : rs) { n++; mx = Math.max(mx, r.getInt(0)); }
                    Row v = s.execute("SELECT v FROM u10.t WHERE pk = " + p + " AND ck = 0").one();
                    int vb = v == null ? -1 : v.getBytesUnsafe("v").remaining();
                    System.out.println("verify pk=" + p + " rows=" + n + " maxCk=" + mx + " v0Bytes=" + vb + (n == 65536 && vb == 16384 ? " OK" : " SHORT"));
                }
            }
            return;
        }
        if (a[0].equals("one")) {
            int pk = Integer.parseInt(a[2]), n = Integer.parseInt(a[3]); String fs = a[4], kind = a[5];
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement ps = s.prepare(q(kind)); ps.setConsistencyLevel(ConsistencyLevel.ONE);
                long t0 = System.nanoTime();
                try {
                    BoundStatement bs = ps.bind(pk, n); bs.setFetchSize(fetch(fs));
                    ResultSet rs = s.execute(bs);
                    long[] r = res(rs, kind);
                    System.out.println("one pk=" + pk + " n=" + n + " fetch=" + fs + " kind=" + kind + " OK result=" + r[0] + " firstPageRows=" + r[1]
                                       + " ms=" + (System.nanoTime() - t0) / 1000000 + " pagingState=" + (rs.getExecutionInfo().getPagingState() != null)
                                       + " warnings=" + rs.getExecutionInfo().getWarnings());
                } catch (Exception e) {
                    System.out.println("one pk=" + pk + " n=" + n + " fetch=" + fs + " kind=" + kind + " ERROR ms=" + (System.nanoTime() - t0) / 1000000 + " " + err(e));
                }
            }
            return;
        }
        if (a[0].equals("cal")) {
            String fs = a[2]; int reps = Integer.parseInt(a[3]);
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                PreparedStatement ps = s.prepare(q("agg")); ps.setConsistencyLevel(ConsistencyLevel.ONE);
                int i = 0;
                for (String ns : a[4].split(",")) {
                    int n = Integer.parseInt(ns);
                    for (int k = 0; k < reps; k++, i++) {
                        int pk = i % 8; long t0 = System.nanoTime();
                        try {
                            BoundStatement bs = ps.bind(pk, n); bs.setFetchSize(fetch(fs));
                            long[] r = res(s.execute(bs), "agg");
                            System.out.println("cal " + System.currentTimeMillis() + " fetch=" + fs + " n=" + n + " pk=" + pk + " OK count=" + r[0]
                                               + " correct=" + (r[0] == n) + " ms=" + (System.nanoTime() - t0) / 1000000);
                        } catch (Exception e) {
                            System.out.println("cal " + System.currentTimeMillis() + " fetch=" + fs + " n=" + n + " pk=" + pk + " ERROR ms="
                                               + (System.nanoTime() - t0) / 1000000 + " " + err(e));
                        }
                        Thread.sleep(1500);
                    }
                }
            }
            return;
        }
        // run
        int conns = Integer.parseInt(a[2]); String[] steps = a[3].split(","); final int fs = fetch(a[4]); final String kind = a[5];
        Cluster c = cluster(host, conns); Session s = c.connect();
        PreparedStatement ps = s.prepare(q(kind)); ps.setConsistencyLevel(ConsistencyLevel.ONE);
        AtomicLong done = new AtomicLong(), ok = new AtomicLong(), correct = new AtomicLong();
        AtomicLong[] errs = {new AtomicLong(), new AtomicLong(), new AtomicLong()};
        AtomicInteger inflight = new AtomicInteger(), curN = new AtomicInteger(0);
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        Semaphore sem = new Semaphore(0);
        AtomicInteger target = new AtomicInteger(0);
        AtomicBoolean stop = new AtomicBoolean(false);
        Thread gen = new Thread(() -> {
            long i = 0;
            while (!stop.get()) {
                try { if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue; } catch (InterruptedException e) { return; }
                if (stop.get()) { sem.release(); return; }
                inflight.incrementAndGet();
                final long t0 = System.nanoTime(); final int n = curN.get(); final int pk = (int) (i++ % 8);
                BoundStatement bs = ps.bind(pk, n); bs.setFetchSize(fs);
                ResultSetFuture f = s.executeAsync(bs);
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        long[] r = res(rs, kind);
                        ok.incrementAndGet(); if (r[0] == n) correct.incrementAndGet(); else lastErr.set("WRONG result=" + r[0] + " n=" + n);
                        lat.add((System.nanoTime() - t0) / 1000); done.incrementAndGet();
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        errs[errClass(e)].incrementAndGet(); lastErr.set(err(e)); done.incrementAndGet();
                        lat.add((System.nanoTime() - t0) / 1000);
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_c,step_n,inflight,done,ok_s,correct_s,err_rt_s,err_rf_s,err_other_s,mean_ms,max_ms,lastErr");
        long tStart = System.currentTimeMillis(); long lOk = 0, lCor = 0; long[] lE = new long[3];
        for (String st : steps) {
            String[] kv = st.split(":"); int cc = Integer.parseInt(kv[0]); int n = Integer.parseInt(kv[1]); long secs = Long.parseLong(kv[2]);
            curN.set(n);
            int d = cc - target.getAndSet(cc);
            if (d > 0) sem.release(d); else if (d < 0) sem.acquireUninterruptibly(-d);
            for (long k = 0; k < secs; k++) {
                Thread.sleep(1000);
                long o = ok.get(), co = correct.get(); long[] e = {errs[0].get(), errs[1].get(), errs[2].get()};
                List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x);
                double mean = l.isEmpty() ? -1 : l.stream().mapToLong(v -> v).average().getAsDouble() / 1000.0;
                double mx = l.isEmpty() ? -1 : Collections.max(l) / 1000.0;
                System.out.printf("%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%.0f,%.0f,%s%n", System.currentTimeMillis(), cc, n, inflight.get(), done.get(),
                                  o - lOk, co - lCor, e[0] - lE[0], e[1] - lE[1], e[2] - lE[2], mean, mx, lastErr.getAndSet(""));
                lOk = o; lCor = co; lE = e;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        System.out.printf("SUMMARY secs=%.0f done=%d ok=%d correct=%d err_rt=%d err_rf=%d err_other=%d inflight_left=%d%n",
                          (System.currentTimeMillis() - tStart) / 1000.0, done.get(), ok.get(), correct.get(), errs[0].get(), errs[1].get(), errs[2].get(), inflight.get());
        c.closeAsync(); System.exit(0);
    }

    static void insert(Session s, PreparedStatement ps, int p, int k, byte[] b, int attempt, Semaphore sem, AtomicLong fails, AtomicLong retries, AtomicLong done) {
        ResultSetFuture f = s.executeAsync(ps.bind(p, k, ByteBuffer.wrap(b)));
        Futures.addCallback(f, new FutureCallback<ResultSet>() {
            public void onSuccess(ResultSet x) { done.incrementAndGet(); sem.release(); }
            public void onFailure(Throwable e) {
                if (attempt < 5) { retries.incrementAndGet(); insert(s, ps, p, k, b, attempt + 1, sem, fails, retries, done); }
                else { fails.incrementAndGet(); System.out.println("load FAIL pk=" + p + " ck=" + k + " " + err(e)); sem.release(); }
            }
        }, MoreExecutors.directExecutor());
    }
}
