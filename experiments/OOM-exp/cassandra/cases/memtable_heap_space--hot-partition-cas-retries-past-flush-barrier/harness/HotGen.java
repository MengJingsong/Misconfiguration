import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

import com.datastax.driver.core.BatchStatement;
import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.ConsistencyLevel;
import com.datastax.driver.core.HostDistance;
import com.datastax.driver.core.NettyOptions;
import com.datastax.driver.core.PoolingOptions;
import com.datastax.driver.core.PreparedStatement;
import com.datastax.driver.core.ProtocolVersion;
import com.datastax.driver.core.Session;
import com.datastax.driver.core.SocketOptions;
import com.datastax.driver.core.exceptions.NoHostAvailableException;
import com.datastax.driver.core.exceptions.OverloadedException;
import com.datastax.driver.core.exceptions.TransportException;
import com.datastax.driver.core.exceptions.WriteTimeoutException;
import com.datastax.shaded.netty.bootstrap.Bootstrap;

/**
 * B18 stage-2 load generator (design §2.5; from the stage-4 LoadGen.java of excess_waste_bytes-...-wastedbytes-2).
 * Driver 3.12.1 shaded from build/lib/jars, protocol V4, CL ONE, node at 127.0.0.1:9042.
 * usage: HotGen <nIPs> <threadsPerIP> <R> <hot|perthread> <seconds> <statsfile> <stopfile> [rateMiBps]
 * One request = an unlogged single-partition batch of R rows INSERT INTO ks.t (pk, ck, v), v = 8,192 random bytes from a pool of
 * 64 arrays, ck from a global counter. hot: pk = 1; perthread: pk = global thread number. One Cluster per source IP
 * 127.0.0.(11+i), bound through NettyOptions.afterBootstrapInitialized; one connection per Cluster, 2,048 requests max, read
 * timeout 30 s; synchronous, one request in flight per thread. On error: count by class, sleep 1 s.
 * Stats each second: ms,req_ok,rows_ok,err_wto,err_ovl,err_tra,err_nha,err_oth,connected_clusters.
 * Stops at <seconds>, at the stopfile, or after 60 s with no success and no connected host. rateMiBps (optional, 0 = none):
 * a global pacing of request starts so that values are sent at <= rateMiBps (C-rm fallback, §2.8).
 */
public class HotGen
{
    static final int VB = 8192;

    public static void main(String[] a) throws Exception
    {
        final int nIPs = Integer.parseInt(a[0]);
        final int tpi = Integer.parseInt(a[1]);
        final int rows = Integer.parseInt(a[2]);
        final String mode = a[3];
        final int secs = Integer.parseInt(a[4]);
        final String stats = a[5];
        final File stop = new File(a[6]);
        final double rate = a.length > 7 ? Double.parseDouble(a[7]) : 0;
        if (!mode.equals("hot") && !mode.equals("perthread"))
            throw new IllegalArgumentException(mode);
        final ByteBuffer[] pool = new ByteBuffer[64];
        Random rnd = new Random(18);
        for (int i = 0; i < pool.length; i++)
        {
            byte[] b = new byte[VB];
            rnd.nextBytes(b);
            pool[i] = ByteBuffer.wrap(b);
        }
        final Cluster[] cls = new Cluster[nIPs];
        final Session[] ss = new Session[nIPs];
        final PreparedStatement[] ps = new PreparedStatement[nIPs];
        for (int i = 0; i < nIPs; i++)
        {
            final String src = "127.0.0." + (11 + i);
            NettyOptions no = new NettyOptions()
            {
                @Override
                public void afterBootstrapInitialized(Bootstrap b)
                {
                    b.localAddress(new InetSocketAddress(src, 0));
                }
            };
            PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1)
                                                    .setMaxRequestsPerConnection(HostDistance.LOCAL, 2048);
            cls[i] = Cluster.builder().addContactPoint("127.0.0.1").withPort(9042).withProtocolVersion(ProtocolVersion.V4)
                            .withPoolingOptions(po).withNettyOptions(no)
                            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(30_000).setConnectTimeoutMillis(30_000))
                            .build();
            ss[i] = cls[i].connect();
            ps[i] = ss[i].prepare("INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)");
            ps[i].setConsistencyLevel(ConsistencyLevel.ONE);
        }
        final AtomicLong ckc = new AtomicLong(), reqs = new AtomicLong(), rowsDone = new AtomicLong();
        final AtomicLong[] errs = new AtomicLong[5];
        for (int i = 0; i < 5; i++) errs[i] = new AtomicLong();
        final AtomicLong lastOk = new AtomicLong(System.currentTimeMillis());
        final AtomicLong nextStart = new AtomicLong(System.currentTimeMillis());
        final long reqNanosAtRate = rate > 0 ? (long) (1e9 * rows * (double) VB / (rate * 1048576.0)) : 0;
        final long end = System.currentTimeMillis() + secs * 1000L;
        final PrintWriter ew = new PrintWriter(new FileWriter(stats + ".errors"));
        final boolean[] halt = new boolean[1];
        Thread[] ts = new Thread[nIPs * tpi];
        for (int t = 0; t < ts.length; t++)
        {
            final int id = t;
            final int ip = t / tpi;
            ts[t] = new Thread(() -> {
                ThreadLocalRandom r = ThreadLocalRandom.current();
                while (System.currentTimeMillis() < end && !stop.exists() && !halt[0])
                {
                    try
                    {
                        if (reqNanosAtRate > 0)
                        {
                            long slot;
                            synchronized (nextStart)
                            {
                                long now = System.nanoTime();
                                slot = Math.max(now, nextStart.get());
                                nextStart.set(slot + reqNanosAtRate);
                            }
                            long w = slot - System.nanoTime();
                            if (w > 0) Thread.sleep(w / 1_000_000, (int) (w % 1_000_000));
                        }
                        int pk = mode.equals("perthread") ? id : 1;
                        BatchStatement b = new BatchStatement(BatchStatement.Type.UNLOGGED);
                        long base = ckc.getAndAdd(rows);
                        for (int i = 0; i < rows; i++)
                            b.add(ps[ip].bind(pk, (int) (base + i), pool[r.nextInt(pool.length)].duplicate()));
                        b.setConsistencyLevel(ConsistencyLevel.ONE);
                        ss[ip].execute(b);
                        reqs.incrementAndGet();
                        rowsDone.addAndGet(rows);
                        lastOk.set(System.currentTimeMillis());
                    }
                    catch (Throwable e)
                    {
                        int k = e instanceof WriteTimeoutException ? 0 : e instanceof OverloadedException ? 1
                              : e instanceof TransportException ? 2 : e instanceof NoHostAvailableException ? 3 : 4;
                        long n = errs[k].incrementAndGet();
                        if (n <= 10) { synchronized (ew) { ew.println(System.currentTimeMillis() + " " + e); ew.flush(); } }
                        try { Thread.sleep(1000); } catch (InterruptedException x) { }
                    }
                }
            });
            ts[t].start();
        }
        if (reqNanosAtRate == 0) nextStart.set(0);
        String why = "end";
        try (PrintWriter w = new PrintWriter(new FileWriter(stats)))
        {
            w.println("ms,req_ok,rows_ok,err_wto,err_ovl,err_tra,err_nha,err_oth,connected");
            while (true)
            {
                boolean alive = false;
                for (Thread t : ts) alive |= t.isAlive();
                int conn = 0;
                for (Session s : ss)
                    if (!s.getState().getConnectedHosts().isEmpty()) conn++;
                long now = System.currentTimeMillis();
                w.println(now + "," + reqs.get() + "," + rowsDone.get() + "," + errs[0].get() + "," + errs[1].get() + ","
                          + errs[2].get() + "," + errs[3].get() + "," + errs[4].get() + "," + conn);
                w.flush();
                if (!alive) break;
                if (stop.exists()) why = "stopfile";
                if (now - lastOk.get() > 60_000 && conn == 0 && !halt[0])
                {
                    halt[0] = true;
                    why = "stalled";
                }
                Thread.sleep(1000);
            }
        }
        long e = 0;
        for (AtomicLong x : errs) e += x.get();
        System.out.println("{\"hotgen\":\"done\",\"stopped\":\"" + why + "\",\"requests\":" + reqs.get() + ",\"rows\":" + rowsDone.get()
                           + ",\"errors\":" + e + ",\"payload_bytes\":" + rowsDone.get() * (long) VB + "}");
        System.out.flush();
        ew.close();
        // closing the clusters can hang when the node is gone; exit directly
        System.exit(0);
    }
}
