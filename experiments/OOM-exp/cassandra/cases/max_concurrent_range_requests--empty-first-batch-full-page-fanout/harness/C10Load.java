// C10 client (pc91, loopback), adapted from U4Load. Java driver 3.12.1 (shaded), protocol v4, CL ONE, WhiteListPolicy
// -> 127.0.0.1:9042 only, read timeout 60 s, FallthroughRetryPolicy.
//   java C10Load schema   <host>
//   java C10Load load     <host> <N> <Thot> <conc>      pk 0..N-1, v = 2,048 B from Random(pk), b = token(pk) > Thot ? 1 : 0
//   java C10Load tokcheck <host>                          20 keys: client token vs SELECT token(pk)
//   java C10Load trace    <host> <test|M>                 one traced query (first page), events + rows + token range of rows
//   java C10Load run      <host> <conns> <steps> <test|M> closed loop, steps "Q:secs,...", first page only, fetch 5,000
// run CSV (one line per second):
//   t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,e_rto,e_rfail,e_unav,e_opto,e_other,lastErr
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import org.apache.cassandra.utils.MurmurHash;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class C10Load {
    static final int FETCH = 5000;
    static final String TEST = "SELECT * FROM c10.t WHERE b = 1 ALLOW FILTERING";
    static final String CTRL_M = "SELECT * FROM c10.t WHERE b >= 0 ALLOW FILTERING";

    static Cluster cluster(String host, int conns) {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
            .setMaxRequestsPerConnection(HostDistance.LOCAL, 4096).setMaxQueueSize(65536);
        return Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                Collections.singletonList(new java.net.InetSocketAddress(host, 9042))))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(30000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withPoolingOptions(po).withoutJMXReporting().build();
    }

    static long token(long pk) {
        ByteBuffer k = ByteBuffer.allocate(8); k.putLong(0, pk);
        long[] h = new long[2]; MurmurHash.hash3_x64_128(k, 0, 8, 0, h);
        return h[0] == Long.MIN_VALUE ? Long.MAX_VALUE : h[0];
    }

    static String q(String which) { return which.equals("M") ? CTRL_M : TEST; }

    public static void main(String[] a) throws Exception {
        String host = a[1];
        if (a[0].equals("schema")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                s.execute("CREATE KEYSPACE IF NOT EXISTS c10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
                s.execute("CREATE TABLE IF NOT EXISTS c10.t (pk bigint PRIMARY KEY, b int, v blob)");
                System.out.println("schema ok");
            }
            return;
        }
        if (a[0].equals("load")) {
            long n = Long.parseLong(a[2]); long thot = Long.parseLong(a[3]); int conc = Integer.parseInt(a[4]);
            try (Cluster c = cluster(host, 2); Session s = c.connect()) {
                PreparedStatement ps = s.prepare("INSERT INTO c10.t (pk, b, v) VALUES (?, ?, ?)");
                ps.setConsistencyLevel(ConsistencyLevel.ONE);
                Semaphore sem = new Semaphore(conc); AtomicLong err = new AtomicLong(); long hot = 0;
                for (long pk = 0; pk < n; pk++) {
                    byte[] b = new byte[2048]; new Random(pk).nextBytes(b);
                    int bv = token(pk) > thot ? 1 : 0; hot += bv;
                    sem.acquireUninterruptibly();
                    ResultSetFuture f = s.executeAsync(ps.bind(pk, bv, ByteBuffer.wrap(b)));
                    Futures.addCallback(f, new FutureCallback<ResultSet>() {
                        public void onSuccess(ResultSet x) { sem.release(); }
                        public void onFailure(Throwable e) { err.incrementAndGet(); System.out.println("load err " + e); sem.release(); }
                    }, MoreExecutors.directExecutor());
                    if (pk % 100000 == 0) System.out.println("loaded " + pk + " " + new Date());
                }
                sem.acquireUninterruptibly(conc);
                System.out.println("load ok N=" + n + " Thot=" + thot + " b1=" + hot + " b0=" + (n - hot) + " errors=" + err.get());
            }
            return;
        }
        if (a[0].equals("tokcheck")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                int bad = 0; Random r = new Random(7);
                for (int i = 0; i < 20; i++) {
                    long pk = i < 2 ? i : (long) r.nextInt(1000000);
                    long srv = s.execute("SELECT token(pk) FROM c10.t WHERE pk=" + pk).one().getLong(0);
                    long cl = token(pk); if (srv != cl) bad++;
                    System.out.println("pk=" + pk + " server=" + srv + " client=" + cl + (srv == cl ? " ok" : " MISMATCH"));
                }
                System.out.println("tokcheck mismatches=" + bad);
            }
            return;
        }
        if (a[0].equals("trace")) {
            try (Cluster c = cluster(host, 1); Session s = c.connect()) {
                Statement st = new SimpleStatement(q(a[2])).setFetchSize(FETCH).setConsistencyLevel(ConsistencyLevel.ONE).enableTracing();
                long t0 = System.nanoTime();
                ResultSet rs = s.execute(st);
                int n = rs.getAvailableWithoutFetching(); long bytes = 0, tmin = Long.MAX_VALUE, tmax = Long.MIN_VALUE;
                for (int i = 0; i < n; i++) {
                    Row row = rs.one(); ByteBuffer v = row.getBytesUnsafe("v"); if (v != null) bytes += v.remaining();
                    long t = token(row.getLong("pk")); tmin = Math.min(tmin, t); tmax = Math.max(tmax, t);
                }
                long ms = (System.nanoTime() - t0) / 1000000;
                System.out.println("trace query=" + a[2] + " rows=" + n + " valueBytes=" + bytes + " ms=" + ms + " rowTokenMin=" + tmin + " rowTokenMax=" + tmax);
                QueryTrace tr = rs.getExecutionInfo().getQueryTrace();
                for (QueryTrace.Event e : tr.getEvents())
                    System.out.println("  ev " + e.getSourceElapsedMicros() + "us " + e.getSource() + " [" + e.getThreadName() + "] " + e.getDescription());
                System.out.println("trace duration_us=" + tr.getDurationMicros());
            }
            return;
        }
        // run
        int conns = Integer.parseInt(a[2]); String[] steps = a[3].split(","); String which = a[4];
        Cluster c = cluster(host, conns); Session s = c.connect();
        PreparedStatement ps = s.prepare(q(which));
        ps.setConsistencyLevel(ConsistencyLevel.ONE);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong(), bytes = new AtomicLong();
        AtomicLong eRto = new AtomicLong(), eRf = new AtomicLong(), eUn = new AtomicLong(), eOpto = new AtomicLong(), eOth = new AtomicLong();
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
                BoundStatement bs = ps.bind(); bs.setFetchSize(FETCH);
                ResultSetFuture f = s.executeAsync(bs);
                Futures.addCallback(f, new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet rs) {
                        long b = 0; int n = rs.getAvailableWithoutFetching();
                        for (int i = 0; i < n; i++) { ByteBuffer v = rs.one().getBytesUnsafe("v"); if (v != null) b += v.remaining(); }
                        rowsLast.set(n); bytes.addAndGet(b); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000);
                        inflight.decrementAndGet(); sem.release();
                    }
                    public void onFailure(Throwable e) {
                        err.incrementAndGet();
                        if (e instanceof ReadTimeoutException) eRto.incrementAndGet();
                        else if (e instanceof ReadFailureException) eRf.incrementAndGet();
                        else if (e instanceof UnavailableException) eUn.incrementAndGet();
                        else if (e instanceof OperationTimedOutException) eOpto.incrementAndGet();
                        else eOth.incrementAndGet();
                        lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '));
                        inflight.decrementAndGet(); sem.release();
                    }
                }, MoreExecutors.directExecutor());
            }
        });
        gen.setDaemon(true); gen.start();
        System.out.println("t,step_N,inflight,ok,err,ok_s,MBps,p50ms,p99ms,rowsLastRead,e_rto,e_rfail,e_unav,e_opto,e_other,lastErr");
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
                System.out.printf("%d,%d,%d,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), n, inflight.get(), o, err.get(),
                                  o - lastOk, (b - lastBytes) / 1048576.0, p50, p99, rowsLast.get(),
                                  eRto.get(), eRf.get(), eUn.get(), eOpto.get(), eOth.get(), lastErr.getAndSet(""));
                lastOk = o; lastBytes = b;
            }
        }
        stop.set(true);
        long w = System.currentTimeMillis() + 30000;
        while (inflight.get() > 0 && System.currentTimeMillis() < w) Thread.sleep(200);
        System.out.printf("SUMMARY secs=%.0f ok=%d err=%d bytesMB=%.0f inflight_left=%d rto=%d rfail=%d unav=%d opto=%d other=%d%n",
                          (System.currentTimeMillis() - tStart) / 1000.0, ok.get(), err.get(), bytes.get() / 1048576.0, inflight.get(),
                          eRto.get(), eRf.get(), eUn.get(), eOpto.get(), eOth.get());
        c.closeAsync(); System.exit(0);
    }
}
