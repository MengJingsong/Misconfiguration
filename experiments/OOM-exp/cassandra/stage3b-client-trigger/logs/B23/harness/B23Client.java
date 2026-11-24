// B23 stage 3-b confirm client (native protocol v4, DataStax java driver 3.12.1 shaded from the build's lib/).
// Every request goes to ONE whitelisted coordinator (n1) through a login role (PasswordAuthenticator).
//   admin  <host> <user> <pass> <cqlfile>                         run each ';'-terminated statement, print result or error
//   attack <host> <user> <pass> <bindIP> <N> <inflight> <size> <ks.table> <exclude-ip> <outlog>
//          writes N rows of <size>-byte blob values at CL ONE, <inflight> concurrent, no retries; the partition keys are chosen
//          client-side so that the coordinator <exclude-ip> is not a replica (driver Metadata.getReplicas = the ring as read by
//          this role from system.local / system.peers / system_schema). One line per second to <outlog>.
//   victim <host> <user> <pass> <bindIP> <rate/s> <outlog> <stopfile>
//          steady load on vks.t: rate/2 writes (100 B) + rate/2 reads per second at CL ONE until <stopfile> exists;
//          one line per request: start_ms op ok(1/0) latency_ms error-class
import com.datastax.driver.core.*;
import com.datastax.driver.core.exceptions.*;
import com.datastax.driver.core.policies.*;
import com.datastax.shaded.netty.bootstrap.Bootstrap;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class B23Client
{
    static Cluster cluster(String host, String u, String p, String bind, int conns)
    {
        InetSocketAddress coord = new InetSocketAddress(host, 9042);
        Cluster.Builder b = Cluster.builder().addContactPointsWithPorts(coord).withCredentials(u, p)
            .withProtocolVersion(ProtocolVersion.V4)
            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(), Collections.singletonList(coord)))
            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
            .withSocketOptions(new com.datastax.driver.core.SocketOptions().setReadTimeoutMillis(12000).setConnectTimeoutMillis(5000))
            .withPoolingOptions(new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, conns, conns)
                                .setMaxRequestsPerConnection(HostDistance.LOCAL, 32768))
            .withoutJMXReporting().withoutMetrics();
        if (bind != null && !bind.equals("-"))
        {
            final InetAddress ba;
            try { ba = InetAddress.getByName(bind); } catch (Exception e) { throw new RuntimeException(e); }
            b.withNettyOptions(new NettyOptions() {
                @Override public void afterBootstrapInitialized(Bootstrap bs) { bs.localAddress(new InetSocketAddress(ba, 0)); }
            });
        }
        return b.build();
    }

    public static void main(String[] a) throws Exception
    {
        switch (a[0])
        {
            case "admin": admin(a); break;
            case "attack": attack(a); break;
            case "victim": victim(a); break;
            default: throw new IllegalArgumentException(a[0]);
        }
    }

    static void admin(String[] a) throws Exception
    {
        try (Cluster c = cluster(a[1], a[2], a[3], "-", 1); Session s = c.connect())
        {
            String all = new String(Files.readAllBytes(Paths.get(a[4])));
            for (String st : all.split(";"))
            {
                st = st.replaceAll("(?m)^\\s*--.*$", "").trim();
                if (st.isEmpty()) continue;
                System.out.println("[" + a[2] + "] " + st.replaceAll("PASSWORD = '[^']*'", "PASSWORD = '***'"));
                try
                {
                    ResultSet rs = s.execute(new SimpleStatement(st).setConsistencyLevel(ConsistencyLevel.ONE));
                    int n = 0;
                    for (Row r : rs) { System.out.println("   row: " + r); if (++n > 50) break; }
                    System.out.println("   OK");
                }
                catch (Exception e) { System.out.println("   ERROR " + e.getClass().getSimpleName() + ": " + e.getMessage()); }
            }
        }
    }

    static void attack(String[] a) throws Exception
    {
        String host = a[1], u = a[2], p = a[3], bind = a[4], table = a[8], excl = a[9];
        long N = Long.parseLong(a[5]); int inflight = Integer.parseInt(a[6]); int size = Integer.parseInt(a[7]);
        PrintStream out = new PrintStream(new FileOutputStream(a[10]), true);
        Cluster c = cluster(host, u, p, bind, 8);
        Session s = c.connect();
        String ks = table.split("\\.")[0];
        Metadata md = c.getMetadata();
        out.println("# ring as seen by " + u + ": hosts " + md.getAllHosts() + " partitioner " + md.getPartitioner());
        for (Host h : md.getAllHosts()) out.println("# host " + h.getAddress() + " state " + (h.isUp() ? "up" : "down") + " tokens " + h.getTokens().size());
        PreparedStatement ps = s.prepare("INSERT INTO " + table + " (key, v) VALUES (?, ?)");
        ps.setConsistencyLevel(ConsistencyLevel.ONE);
        byte[] val = new byte[size]; new Random(23).nextBytes(val);
        ByteBuffer vb = ByteBuffer.wrap(val);
        InetAddress ex = InetAddress.getByName(excl);
        Semaphore sem = new Semaphore(inflight);
        AtomicLong ok = new AtomicLong(), err = new AtomicLong();
        ConcurrentHashMap<String, AtomicLong> errs = new ConcurrentHashMap<>();
        AtomicLong issued = new AtomicLong(), skipped = new AtomicLong();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        ScheduledExecutorService ses = Executors.newSingleThreadScheduledExecutor();
        long t0 = System.currentTimeMillis();
        out.println("epoch_ms el_s issued ok err inflight keys_skipped errs_by_class");
        ses.scheduleAtFixedRate(() -> out.println(System.currentTimeMillis() + " " + (System.currentTimeMillis() - t0) / 1000 + " " + issued.get() + " " + ok.get() + " " + err.get()
                                                  + " " + (inflight - sem.availablePermits()) + " " + skipped.get() + " " + errs), 1, 1, TimeUnit.SECONDS);
        long k = 0;
        while (issued.get() < N)
        {
            ByteBuffer key = ByteBuffer.allocate(8).putLong(0, k++);
            boolean onCoord = false;
            for (Host h : md.getReplicas(Metadata.quote(ks), key)) if (h.getAddress().equals(ex)) onCoord = true;
            if (onCoord) { skipped.incrementAndGet(); continue; }
            sem.acquire();
            issued.incrementAndGet();
            ResultSetFuture f = s.executeAsync(ps.bind(key, vb.duplicate()));
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet r) { ok.incrementAndGet(); sem.release(); }
                public void onFailure(Throwable t) {
                    err.incrementAndGet(); errs.computeIfAbsent(t.getClass().getSimpleName(), x -> new AtomicLong()).incrementAndGet();
                    if (!t.toString().equals(lastErr.get())) { lastErr.set(t.toString()); System.err.println(System.currentTimeMillis() + " " + t); }
                    sem.release();
                }
            }, MoreExecutors.directExecutor());
        }
        sem.acquire(inflight);
        Thread.sleep(1100);
        out.println("# done issued=" + issued.get() + " ok=" + ok.get() + " err=" + err.get() + " skipped=" + skipped.get() + " errs=" + errs);
        ses.shutdownNow(); s.close(); c.close();
        System.exit(0);
    }

    static void victim(String[] a) throws Exception
    {
        String host = a[1], u = a[2], p = a[3], bind = a[4]; int rate = Integer.parseInt(a[5]);
        PrintStream out = new PrintStream(new BufferedOutputStream(new FileOutputStream(a[6]), 1 << 16), false);
        Path stop = Paths.get(a[7]);
        Cluster c = null; Session s = null;
        while (s == null)
        {
            try { c = cluster(host, u, p, bind, 1); s = c.connect(); }
            catch (Exception e) { System.err.println("connect: " + e); if (c != null) c.close(); c = null; Thread.sleep(1000); }
        }
        PreparedStatement w = s.prepare("INSERT INTO vks.t (k, v) VALUES (?, ?)"); w.setConsistencyLevel(ConsistencyLevel.ONE);
        PreparedStatement r = s.prepare("SELECT v FROM vks.t WHERE k = ?"); r.setConsistencyLevel(ConsistencyLevel.ONE);
        ByteBuffer v = ByteBuffer.wrap(new byte[100]);
        final Session fs = s;
        ScheduledExecutorService ses = Executors.newScheduledThreadPool(2);
        AtomicLong seq = new AtomicLong();
        synchronized (out) { out.println("start_ms op ok lat_ms err"); }
        ses.scheduleAtFixedRate(() -> {
            long i = seq.getAndIncrement(); boolean write = (i % 2 == 0);
            long st = System.currentTimeMillis();
            ResultSetFuture f;
            try { f = write ? fs.executeAsync(w.bind((int) ((i / 2) % 1000), v.duplicate())) : fs.executeAsync(r.bind((int) ((i / 2) % 1000))); }
            catch (Exception e) { synchronized (out) { out.println(st + " " + (write ? "W" : "R") + " 0 0 " + e.getClass().getSimpleName()); } return; }
            Futures.addCallback(f, new FutureCallback<ResultSet>() {
                public void onSuccess(ResultSet x) { synchronized (out) { out.println(st + " " + (write ? "W" : "R") + " 1 " + (System.currentTimeMillis() - st) + " -"); } }
                public void onFailure(Throwable t) { synchronized (out) { out.println(st + " " + (write ? "W" : "R") + " 0 " + (System.currentTimeMillis() - st) + " " + t.getClass().getSimpleName()); } }
            }, MoreExecutors.directExecutor());
        }, 0, 1_000_000L / rate, TimeUnit.MICROSECONDS);
        while (!Files.exists(stop)) { Thread.sleep(500); synchronized (out) { out.flush(); } }
        ses.shutdown();
        Thread.sleep(13000); // let outstanding requests complete or time out (driver read timeout 12 s)
        synchronized (out) { out.flush(); }
        System.exit(0);
    }
}
