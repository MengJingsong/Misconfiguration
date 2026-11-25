// 3-b confirm C4 (pc99, 2026-11-24): one client program, Java driver 3.12.1 (protocol v4), native protocol only.
// Host/port from -Dc4.host / -Dc4.port; role from -Dc4.user / -Dc4.pass (unset = no credentials).
//   cql <file>                         run one CQL statement per line (lines starting with -- are echoed), print OK/ERR + rows
//   load <ks.table> <start> <n> <inflight>
//                                      INSERT INTO <ks.table> (pk, v) VALUES (?, ?): pk = 988-char prefix + 12-digit index
//                                      (1,000-byte text keys, as stage 2), v int. One CSV line per second:
//                                      t,sent,ok,err,inflight,lastErr. Ends after n rows, or when no write has succeeded for
//                                      20 s (node gone), printing SUMMARY.
//   vpreload <rows>                    victim: 10,000 rows of 100 B into vks.kv
//   victim <rate> <maxSecs> <stopFile> victim: open loop at <rate> ops/s (half reads, half 100-B writes, CL QUORUM, read
//                                      timeout 12 s, no retries). Connects in the background and retries every 2 s; ticks
//                                      before a session exists count as e_noconn. CSV per second:
//                                      t,sess,issued,ok,err,p50ms,p99ms,maxms,inflight,e_rto,e_wto,e_unav,e_opto,e_nohost,e_auth,e_noconn,e_other,lastErr
//   mon <jmxport> <csv> <stopFile> <ks> <table>
//                                      admin-side diagnostic (JMX, not an attacker step), every 1 s:
//                                      t,pool_bytes,capacity_mb,avg_interval,tbl_summary_bytes,tbl_sstables,tbl_bf_bytes,tbl_cmeta_bytes,pending_compactions,heap_used
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;

public class C4Client {
    static String HOST = System.getProperty("c4.host", "127.0.0.1");
    static int PORT = Integer.getInteger("c4.port", 29050);

    static Cluster cluster() {
        Cluster.Builder b = Cluster.builder().addContactPoint(HOST).withPort(PORT).withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new RoundRobinPolicy())
            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(12000).setConnectTimeoutMillis(5000))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withReconnectionPolicy(new ConstantReconnectionPolicy(2000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 2, 2)
                .setMaxRequestsPerConnection(HostDistance.LOCAL, 2048).setMaxQueueSize(8192))
            .withoutJMXReporting();
        String u = System.getProperty("c4.user");
        if (u != null && !u.isEmpty()) b = b.withCredentials(u, System.getProperty("c4.pass", ""));
        return b.build();
    }

    static String PREFIX;
    static { StringBuilder sb = new StringBuilder(); while (sb.length() < 988) sb.append("tenant/app/objects/2026/11/24/"); PREFIX = sb.substring(0, 988); }
    static String key(long i) { return PREFIX + String.format("%012d", i); }

    public static void main(String[] a) throws Exception {
        switch (a[0]) {
            case "cql": cql(a[1]); break;
            case "load": load(a[1], Long.parseLong(a[2]), Long.parseLong(a[3]), Integer.parseInt(a[4])); break;
            case "vpreload": vpreload(Integer.parseInt(a[1])); break;
            case "victim": victim(Integer.parseInt(a[1]), Long.parseLong(a[2]), new File(a[3])); break;
            case "mon": mon(Integer.parseInt(a[1]), a[2], new File(a[3]), a[4], a[5]); break;
            default: throw new IllegalArgumentException(a[0]);
        }
        System.exit(0);
    }

    static void cql(String file) throws Exception {
        Cluster c = cluster(); Session s;
        try { s = c.connect(); }
        catch (Exception e) { System.out.println("CONNECT-ERR " + e.getClass().getSimpleName() + ": " + e.getMessage()); c.close(); return; }
        System.out.println("CONNECTED as " + System.getProperty("c4.user", "(no credentials)"));
        for (String line : Files.readAllLines(Paths.get(file))) {
            String st = line.trim();
            if (st.isEmpty()) continue;
            if (st.startsWith("--")) { System.out.println(st); continue; }
            try {
                ResultSet rs = s.execute(new SimpleStatement(st).setReadTimeoutMillis(60000));
                System.out.println("OK  " + st);
                int n = 0;
                for (Row r : rs) { if (n++ >= 60) { System.out.println("    ..."); break; } System.out.println("    " + r.toString()); }
            } catch (Exception e) {
                System.out.println("ERR " + st + "\n    -> " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace('\n', ' '));
            }
        }
        c.close();
    }

    static void load(String tbl, long start, long n, int inflight) throws Exception {
        Cluster c = cluster(); Session s = c.connect();
        PreparedStatement w = s.prepare("INSERT INTO " + tbl + " (pk, v) VALUES (?, ?)");
        w.setConsistencyLevel(ConsistencyLevel.ONE);
        Semaphore sem = new Semaphore(inflight);
        AtomicLong sent = new AtomicLong(), ok = new AtomicLong(), err = new AtomicLong();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        AtomicLong lastOk = new AtomicLong(System.currentTimeMillis());
        AtomicBoolean stop = new AtomicBoolean();
        System.out.println("t,sent,ok,err,inflight,lastErr");
        Thread rep = new Thread(() -> {
            long t0 = System.currentTimeMillis();
            while (!stop.get()) {
                try { Thread.sleep(1000 - (System.currentTimeMillis() - t0) % 1000); } catch (InterruptedException e) { return; }
                System.out.printf("%d,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), sent.get(), ok.get(), err.get(), inflight - sem.availablePermits(), lastErr.getAndSet(""));
                System.out.flush();
            }
        });
        rep.setDaemon(true); rep.start();
        String why = "n reached";
        for (long i = start; i < start + n; i++) {
            while (!sem.tryAcquire(1, TimeUnit.SECONDS)) {
                if (System.currentTimeMillis() - lastOk.get() > 20000) break;
            }
            if (System.currentTimeMillis() - lastOk.get() > 20000) { why = "no success for 20 s"; break; }
            sent.incrementAndGet();
            ResultSetFuture f;
            try { f = s.executeAsync(w.bind(key(i), (int) i)); }
            catch (Exception e) { err.incrementAndGet(); lastErr.set(e.getClass().getSimpleName()); sem.release(); continue; }
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); lastOk.set(System.currentTimeMillis()); sem.release(); }
                public void onFailure(Throwable t) { err.incrementAndGet(); lastErr.set(t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()).replace(',', ';').replace('\n', ' ')); sem.release(); }
            }, MoreExecutors.directExecutor());
        }
        long dl = System.currentTimeMillis() + 15000;
        while (sem.availablePermits() < inflight && System.currentTimeMillis() < dl) Thread.sleep(100);
        stop.set(true); Thread.sleep(1100);
        System.out.printf("SUMMARY end=%s sent=%d ok=%d err=%d lastKeyIndex=%d%n", why, sent.get(), ok.get(), err.get(), start + sent.get() - 1);
        c.closeAsync();
    }

    static void vpreload(int n) throws Exception {
        try (Cluster c = cluster(); Session s = c.connect()) {
            PreparedStatement w = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)");
            w.setConsistencyLevel(ConsistencyLevel.QUORUM);
            Semaphore sem = new Semaphore(32); AtomicLong e = new AtomicLong();
            for (int k = 0; k < n; k++) {
                sem.acquireUninterruptibly();
                Futures.addCallback(s.executeAsync(w.bind(k, ByteBuffer.wrap(new byte[100]))), new FutureCallback<ResultSet>() {
                    public void onSuccess(ResultSet r) { sem.release(); }
                    public void onFailure(Throwable t) { e.incrementAndGet(); sem.release(); }
                }, MoreExecutors.directExecutor());
            }
            sem.acquireUninterruptibly(32);
            System.out.println("victim preload rows=" + n + " errors=" + e.get());
        }
    }

    static final int VROWS = 10000;
    static volatile Session vs; static volatile PreparedStatement vrd, vwr;

    static void victim(int rate, long maxSecs, File stop) throws Exception {
        final AtomicLong issued = new AtomicLong(), ok = new AtomicLong(), err = new AtomicLong();
        final AtomicLong rto = new AtomicLong(), wto = new AtomicLong(), unav = new AtomicLong(), opto = new AtomicLong(),
            nohost = new AtomicLong(), auth = new AtomicLong(), noconn = new AtomicLong(), other = new AtomicLong();
        final AtomicInteger inflight = new AtomicInteger();
        final ConcurrentLinkedQueue<Long> lat = new ConcurrentLinkedQueue<>();
        final AtomicReference<String> lastErr = new AtomicReference<>("");
        Thread con = new Thread(() -> {
            while (vs == null) {
                Cluster c = cluster();
                try {
                    Session s = c.connect();
                    PreparedStatement r = s.prepare("SELECT v FROM vks.kv WHERE k = ?"); r.setConsistencyLevel(ConsistencyLevel.QUORUM);
                    PreparedStatement w = s.prepare("INSERT INTO vks.kv (k, v) VALUES (?, ?)"); w.setConsistencyLevel(ConsistencyLevel.QUORUM);
                    vrd = r; vwr = w; vs = s;
                    System.err.println("victim connected at " + System.currentTimeMillis());
                } catch (Exception e) {
                    lastErr.set("connect: " + e.getClass().getSimpleName());
                    c.close();
                    try { Thread.sleep(2000); } catch (InterruptedException ie) { return; }
                }
            }
        });
        con.setDaemon(true); con.start();
        ScheduledExecutorService ex = Executors.newScheduledThreadPool(1);
        AtomicLong seq = new AtomicLong();
        ex.scheduleAtFixedRate(() -> {
            issued.incrementAndGet();
            Session s = vs;
            if (s == null) { err.incrementAndGet(); noconn.incrementAndGet(); return; }
            if (inflight.get() >= 3000) { err.incrementAndGet(); other.incrementAndGet(); lastErr.set("client-side backlog cap"); return; }
            long q = seq.incrementAndGet(); int k = (int) ((q * 7919) % VROWS);
            Statement st = (q % 2 == 0) ? vrd.bind(k) : vwr.bind(k, ByteBuffer.wrap(new byte[100]));
            final long t0 = System.nanoTime();
            inflight.incrementAndGet();
            FutureCallback<ResultSet> cb = new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); lat.add((System.nanoTime() - t0) / 1000); inflight.decrementAndGet(); }
                public void onFailure(Throwable e) {
                    err.incrementAndGet(); inflight.decrementAndGet();
                    if (e instanceof ReadTimeoutException) rto.incrementAndGet();
                    else if (e instanceof WriteTimeoutException) wto.incrementAndGet();
                    else if (e instanceof UnavailableException) unav.incrementAndGet();
                    else if (e instanceof OperationTimedOutException) opto.incrementAndGet();
                    else if (e instanceof NoHostAvailableException) nohost.incrementAndGet();
                    else if (e instanceof AuthenticationException || e instanceof UnauthorizedException) auth.incrementAndGet();
                    else other.incrementAndGet();
                    lastErr.set(e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace(',', ';').replace('\n', ' '));
                }
            };
            try { Futures.addCallback(s.executeAsync(st), cb, MoreExecutors.directExecutor()); }
            catch (Exception e) { cb.onFailure(e); }
        }, 0, 1000000L / rate, TimeUnit.MICROSECONDS);
        System.out.println("t,sess,issued,ok,err,p50ms,p99ms,maxms,inflight,e_rto,e_wto,e_unav,e_opto,e_nohost,e_auth,e_noconn,e_other,lastErr");
        long t0 = System.currentTimeMillis(), pI = 0, pO = 0, pE = 0;
        while (!stop.exists() && System.currentTimeMillis() - t0 < maxSecs * 1000) {
            Thread.sleep(1000 - (System.currentTimeMillis() - t0) % 1000);
            List<Long> l = new ArrayList<>(); Long v; while ((v = lat.poll()) != null) l.add(v);
            Collections.sort(l);
            double p50 = l.isEmpty() ? -1 : l.get(l.size() / 2) / 1000.0, p99 = l.isEmpty() ? -1 : l.get(Math.min(l.size() - 1, (int) (l.size() * 0.99))) / 1000.0;
            double mx = l.isEmpty() ? -1 : l.get(l.size() - 1) / 1000.0;
            long i = issued.get(), o = ok.get(), e = err.get();
            System.out.printf("%d,V1,%d,%d,%d,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d,%d,%d,%d,%d,%s%n", System.currentTimeMillis(), i - pI, o - pO, e - pE, p50, p99, mx,
                inflight.get(), rto.get(), wto.get(), unav.get(), opto.get(), nohost.get(), auth.get(), noconn.get(), other.get(), lastErr.getAndSet(""));
            System.out.flush();
            pI = i; pO = o; pE = e;
        }
        ex.shutdownNow();
        System.out.printf("SUMMARY V1 issued=%d ok=%d err=%d rto=%d wto=%d unav=%d opto=%d nohost=%d auth=%d noconn=%d other=%d%n",
            issued.get(), ok.get(), err.get(), rto.get(), wto.get(), unav.get(), opto.get(), nohost.get(), auth.get(), noconn.get(), other.get());
    }

    static Object attr(MBeanServerConnection m, String on, String at) {
        try { return m.getAttribute(new ObjectName(on), at); } catch (Exception e) { return ""; }
    }

    static void mon(int port, String csv, File stop, String ks, String tbl) throws Exception {
        PrintWriter pw = new PrintWriter(new FileWriter(csv, true), true);
        pw.println("t,pool_bytes,capacity_mb,avg_interval,tbl_summary_bytes,tbl_sstables,tbl_bf_bytes,tbl_cmeta_bytes,pending_compactions,heap_used");
        String ism = "org.apache.cassandra.db:type=IndexSummaries";
        String t = "org.apache.cassandra.metrics:type=Table,keyspace=" + ks + ",scope=" + tbl + ",name=";
        JMXConnector jc = null; long lastGood = System.currentTimeMillis();
        while (!stop.exists()) {
            long now = System.currentTimeMillis();
            try {
                if (jc == null) jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi"));
                MBeanServerConnection m = jc.getMBeanServerConnection();
                Object mb = m.getAttribute(new ObjectName(ism), "MemoryPoolSizeInMB");
                long pool = Math.round(((Double) mb) * 1024 * 1024);
                CompositeData hu = (CompositeData) attr(m, "java.lang:type=Memory", "HeapMemoryUsage");
                pw.printf("%d,%d,%s,%s,%s,%s,%s,%s,%s,%s%n", now, pool, attr(m, ism, "MemoryPoolCapacityInMB"), attr(m, ism, "AverageIndexInterval"),
                    attr(m, t + "IndexSummaryOffHeapMemoryUsed", "Value"), attr(m, t + "LiveSSTableCount", "Value"),
                    attr(m, t + "BloomFilterOffHeapMemoryUsed", "Value"), attr(m, t + "CompressionMetadataOffHeapMemoryUsed", "Value"),
                    attr(m, "org.apache.cassandra.metrics:type=Compaction,name=PendingTasks", "Value"), hu == null ? "" : hu.get("used"));
                lastGood = now;
            } catch (Exception e) {
                if (jc != null) { try { jc.close(); } catch (Exception ignore) {} jc = null; }
                if (now - lastGood > 600000) break;
            }
            Thread.sleep(Math.max(10, 1000 - (System.currentTimeMillis() - now)));
        }
        pw.close();
    }
}
