// R21 3-b confirm (ms0611, 2026-11-23): the victim tenant's client (B21's 3-b victim, made standalone). Role from env
// R21_USER / R21_PASS (tenant: SELECT, MODIFY on vic.kv only). Java driver 3.12.1, protocol v4, CL ONE, 1 connection to
// 127.0.0.1:9042 (source 127.0.0.1; the attacker uses 127.0.0.11-14), client read timeout 12 s (= native_transport_timeout),
// FallthroughRetryPolicy (no retries: every failure is counted).
//   java R21Victim setup <keys>                        writes keys 0..keys-1 (100-char values)
//   java R21Victim run <writes/s> <reads/s> <stopFile> <maxSecs>
//       open loop at a fixed rate (async; a request is skipped, not queued, when 2,000 are in flight); per second:
//       "V t_ms,sent,ok,err_timeout,err_unavail,err_nohost,err_other,skipped,inflight,p50ms,p99ms,maxms,lastErr"
//       (ok and err_* count completions in that second; latency over successful completions in that second)
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.FallthroughRetryPolicy;
import com.google.common.util.concurrent.*;
import java.io.File;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class R21Victim {
    static final AtomicLong sent = new AtomicLong(), ok = new AtomicLong(), eTo = new AtomicLong(), eUn = new AtomicLong(),
        eNh = new AtomicLong(), eOth = new AtomicLong(), skipped = new AtomicLong();
    static final AtomicInteger inflight = new AtomicInteger();
    static final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
    static final AtomicReference<String> lastErr = new AtomicReference<>("");

    static String val(int k, long n) { StringBuilder sb = new StringBuilder(); while (sb.length() < 100) sb.append(k).append('-').append(n).append('.'); return sb.substring(0, 100); }

    static Cluster cluster() {
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1).setMaxRequestsPerConnection(HostDistance.LOCAL, 2048);
        return Cluster.builder().addContactPoint("127.0.0.1").withPort(9042).withProtocolVersion(ProtocolVersion.V4)
            .withCredentials(System.getenv("R21_USER"), System.getenv("R21_PASS"))
            .withPoolingOptions(po).withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(12_000).setConnectTimeoutMillis(10_000)).build();
    }

    public static void main(String[] a) throws Exception {
        Cluster c = cluster();
        Session s = c.connect();
        if (a[0].equals("setup")) {
            int keys = Integer.parseInt(a[1]);
            PreparedStatement w = s.prepare("INSERT INTO vic.kv (k, v) VALUES (?, ?)");
            for (int k = 0; k < keys; k++) s.execute(w.bind(k, val(k, 0)));
            System.out.println("victim setup ok keys=" + keys + " count=" + s.execute("SELECT count(*) FROM vic.kv").one().getLong(0));
            c.close(); System.exit(0);
        }
        int wps = Integer.parseInt(a[1]), rps = Integer.parseInt(a[2]); File stop = new File(a[3]); long maxSecs = Long.parseLong(a[4]);
        PreparedStatement w = s.prepare("INSERT INTO vic.kv (k, v) VALUES (?, ?)");
        PreparedStatement r = s.prepare("SELECT v FROM vic.kv WHERE k = ?");
        Random rnd = new Random(7);
        ScheduledExecutorService ex = Executors.newScheduledThreadPool(2);
        AtomicLong seq = new AtomicLong();
        Runnable issueW = () -> issue(s, w.bind(rnd.nextInt(1000), val(0, seq.incrementAndGet())));
        Runnable issueR = () -> issue(s, r.bind(rnd.nextInt(1000)));
        if (wps > 0) ex.scheduleAtFixedRate(issueW, 0, 1_000_000L / wps, TimeUnit.MICROSECONDS);
        if (rps > 0) ex.scheduleAtFixedRate(issueR, 500_000L / Math.max(1, rps), 1_000_000L / rps, TimeUnit.MICROSECONDS);
        System.out.println("V t_ms,sent,ok,err_timeout,err_unavail,err_nohost,err_other,skipped,inflight,p50ms,p99ms,maxms,lastErr");
        long t0 = System.currentTimeMillis(), lS = 0, lO = 0, lT = 0, lU = 0, lN = 0, lX = 0, lK = 0;
        while (!stop.exists() && System.currentTimeMillis() - t0 < maxSecs * 1000) {
            Thread.sleep(1000 - (System.currentTimeMillis() - t0) % 1000);
            List<Long> l = new ArrayList<>(); Long x; while ((x = lat.poll()) != null) l.add(x); Collections.sort(l);
            long p50 = l.isEmpty() ? -1 : l.get(l.size() / 2), p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))), mx = l.isEmpty() ? -1 : l.get(l.size() - 1);
            long S = sent.get(), O = ok.get(), T = eTo.get(), U = eUn.get(), N = eNh.get(), X = eOth.get(), K = skipped.get();
            System.out.println("V " + System.currentTimeMillis() + "," + (S - lS) + "," + (O - lO) + "," + (T - lT) + "," + (U - lU) + "," + (N - lN) + "," + (X - lX)
                + "," + (K - lK) + "," + inflight.get() + "," + p50 + "," + p99 + "," + mx + "," + lastErr.getAndSet(""));
            System.out.flush();
            lS = S; lO = O; lT = T; lU = U; lN = N; lX = X; lK = K;
        }
        ex.shutdownNow();
        System.out.println("VSUMMARY secs=" + (System.currentTimeMillis() - t0) / 1000 + " sent=" + sent.get() + " ok=" + ok.get() + " timeout=" + eTo.get()
            + " unavail=" + eUn.get() + " nohost=" + eNh.get() + " other=" + eOth.get() + " skipped=" + skipped.get());
        System.out.flush();
        c.closeAsync(); System.exit(0);
    }

    static void issue(Session s, Statement st) {
        if (inflight.get() >= 2000) { skipped.incrementAndGet(); return; }
        inflight.incrementAndGet(); sent.incrementAndGet();
        final long t0 = System.nanoTime();
        ResultSetFuture f = s.executeAsync(st);
        Futures.addCallback(f, new FutureCallback<ResultSet>() {
            public void onSuccess(ResultSet rs) { inflight.decrementAndGet(); ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000000); }
            public void onFailure(Throwable e) {
                inflight.decrementAndGet();
                if (e instanceof OperationTimedOutException || e instanceof ReadTimeoutException || e instanceof WriteTimeoutException) eTo.incrementAndGet();
                else if (e instanceof UnavailableException) eUn.incrementAndGet();
                else if (e instanceof NoHostAvailableException) eNh.incrementAndGet();
                else eOth.incrementAndGet();
                String m = e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage());
                lastErr.set(m.replace(',', ';').replace('\n', ' ').substring(0, Math.min(160, m.length())));
            }
        }, MoreExecutors.directExecutor());
    }
}
