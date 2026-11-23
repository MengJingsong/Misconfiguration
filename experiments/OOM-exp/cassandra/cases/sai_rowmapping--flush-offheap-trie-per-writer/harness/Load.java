// U13 stage-2 load driver (design §2.5), DataStax Java driver 3.12.1 (lib/cassandra-driver-core-3.12.1-shaded.jar), protocol V4.
// usage: java Load schema <arm M|CTL|INT> <port>
//        java Load load <arm M|CTL|INT> <port> <inflight> <rowsPerBatch> <maxSec> <stopfile> <csv>
// Rows: pk bigint sequential blocks of 1,000 rows (batch b -> pk = b / (1000/rowsPerBatch)); M/INT: ck = 1,000 random
// alphanumeric chars, v uniform 1..1,000,000. CTL: ck = row index within the partition (bigint), pad = 1,000 random
// alphanumeric chars, same v. Unlogged single-partition batches, CL ONE, <inflight> batches outstanding, no retries.
// csv: one cumulative row per second: epoch_s,batches_ok,rows_ok,errors,write_timeouts,outstanding. Stops at maxSec, stopfile, or after
// 120 s without any successful batch while errors occur (node gone; write timeouts while the memtable pool blocks are
// counted and the load continues; fixed 2026-11-21 after C0 run c0 quit on 200 consecutive timeouts). Summary JSON on stdout.
import com.datastax.driver.core.*;
import com.datastax.driver.core.policies.*;
import com.google.common.util.concurrent.*;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class Load
{
    static final String ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    static String rnd(ThreadLocalRandom r, int n)
    {
        char[] c = new char[n];
        for (int i = 0; i < n; i++) c[i] = ALNUM.charAt(r.nextInt(ALNUM.length()));
        return new String(c);
    }

    public static void main(String[] a) throws Exception
    {
        String mode = a[0], arm = a[1];
        int port = Integer.parseInt(a[2]);
        Cluster cl = Cluster.builder().addContactPoint("127.0.0.1").withPort(port).withProtocolVersion(ProtocolVersion.V4)
                            .withRetryPolicy(FallthroughRetryPolicy.INSTANCE)
                            .withLoadBalancingPolicy(new WhiteListPolicy(new RoundRobinPolicy(),
                                                     java.util.Collections.singletonList(new java.net.InetSocketAddress("127.0.0.1", port))))
                            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(60000).setConnectTimeoutMillis(30000))
                            .withQueryOptions(new QueryOptions().setConsistencyLevel(ConsistencyLevel.ONE))
                            .withoutJMXReporting().withoutMetrics().build();
        Session s = cl.connect();
        if (mode.equals("schema"))
        {
            s.execute("CREATE KEYSPACE IF NOT EXISTS u13 WITH replication = {'class':'SimpleStrategy','replication_factor':1}");
            if (arm.equals("CTL"))
                s.execute("CREATE TABLE IF NOT EXISTS u13.t (pk bigint, ck bigint, pad text, v int, PRIMARY KEY (pk, ck))");
            else
                s.execute("CREATE TABLE IF NOT EXISTS u13.t (pk bigint, ck text, v int, PRIMARY KEY (pk, ck))");
            if (!arm.equals("INT"))
                s.execute("CREATE INDEX IF NOT EXISTS t_v ON u13.t (v) USING 'sai'");
            for (Row r : s.execute("SELECT table_name, index_name, options FROM system_schema.indexes WHERE keyspace_name='u13'"))
                System.out.println("index " + r.getString(0) + " " + r.getString(1) + " " + r.getMap(2, String.class, String.class));
            System.out.println(s.execute("SELECT * FROM system_schema.tables WHERE keyspace_name='u13'").one());
            cl.close();
            return;
        }
        int inflight = Integer.parseInt(a[3]), rpb = Integer.parseInt(a[4]);
        long maxMs = Long.parseLong(a[5]) * 1000L;
        File stop = new File(a[6]);
        PrintWriter csv = new PrintWriter(new FileWriter(a[7]), true);
        int bpp = 1000 / rpb;
        PreparedStatement ps = arm.equals("CTL") ? s.prepare("INSERT INTO u13.t (pk, ck, pad, v) VALUES (?, ?, ?, ?)")
                                                 : s.prepare("INSERT INTO u13.t (pk, ck, v) VALUES (?, ?, ?)");
        Semaphore sem = new Semaphore(inflight);
        AtomicLong ok = new AtomicLong(), rows = new AtomicLong(), err = new AtomicLong(), consec = new AtomicLong(), lastOk = new AtomicLong(System.currentTimeMillis());
        AtomicLong tmo = new AtomicLong();
        AtomicReference<String> lastErr = new AtomicReference<>("");
        long t0 = System.currentTimeMillis(), nextCsv = t0 / 1000 + 1;
        long b = 0;
        String why = "maxSec";
        while (true)
        {
            long now = System.currentTimeMillis();
            if (now / 1000 >= nextCsv)
            {
                csv.println((now / 1000) + "," + ok.get() + "," + rows.get() + "," + err.get() + "," + tmo.get() + "," + (inflight - sem.availablePermits()));
                nextCsv = now / 1000 + 1;
                if (stop.exists()) { why = "stopfile"; break; }
            }
            if (now - t0 >= maxMs) { why = "maxSec"; break; }
            if (err.get() > 0 && now - lastOk.get() > 120000) { why = "errors"; break; }
            if (!sem.tryAcquire(200, TimeUnit.MILLISECONDS)) continue;
            ThreadLocalRandom r = ThreadLocalRandom.current();
            long pk = b / bpp, base = (b % bpp) * rpb;
            BatchStatement bs = new BatchStatement(BatchStatement.Type.UNLOGGED);
            for (int i = 0; i < rpb; i++)
            {
                int v = 1 + r.nextInt(1000000);
                if (arm.equals("CTL")) bs.add(ps.bind(pk, base + i, rnd(r, 1000), v));
                else bs.add(ps.bind(pk, rnd(r, 1000), v));
            }
            b++;
            ResultSetFuture f = s.executeAsync(bs);
            Futures.addCallback(f, new FutureCallback<ResultSet>()
            {
                public void onSuccess(ResultSet rs) { ok.incrementAndGet(); rows.addAndGet(rpb); consec.set(0); lastOk.set(System.currentTimeMillis()); sem.release(); }
                public void onFailure(Throwable t) { err.incrementAndGet(); if (t instanceof com.datastax.driver.core.exceptions.WriteTimeoutException) tmo.incrementAndGet(); consec.incrementAndGet(); lastErr.set(t.toString()); sem.release(); }
            }, MoreExecutors.directExecutor());
        }
        sem.tryAcquire(inflight, 70, TimeUnit.SECONDS);
        long el = System.currentTimeMillis() - t0;
        csv.println((System.currentTimeMillis() / 1000) + "," + ok.get() + "," + rows.get() + "," + err.get() + "," + tmo.get() + "," + (inflight - sem.availablePermits()));
        csv.close();
        System.out.println("{\"why\":\"" + why + "\",\"batches_issued\":" + b + ",\"batches_ok\":" + ok.get() + ",\"rows_ok\":" + rows.get()
                           + ",\"errors\":" + err.get() + ",\"write_timeouts\":" + tmo.get() + ",\"elapsed_s\":" + (el / 1000.0) + ",\"rows_per_s\":" + (rows.get() * 1000.0 / el)
                           + ",\"last_error\":\"" + lastErr.get().replace("\"", "'") + "\"}");
        cl.close();
        System.exit(0);
    }
}
