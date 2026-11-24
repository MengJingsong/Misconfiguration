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
import com.datastax.driver.core.ResultSet;
import com.datastax.driver.core.Session;
import com.datastax.driver.core.SocketOptions;
import com.datastax.driver.core.exceptions.NoHostAvailableException;
import com.datastax.driver.core.exceptions.OverloadedException;
import com.datastax.driver.core.exceptions.TransportException;
import com.datastax.driver.core.exceptions.WriteTimeoutException;
import com.datastax.shaded.netty.bootstrap.Bootstrap;

/**
 * R21 3-b confirm (ms0611, 2026-11-23): stage-2 HotGen with ONE change: every Cluster logs in with the role named by env
 * R21_USER / R21_PASS (PasswordAuthenticator; the attacker role holds only SELECT + MODIFY on ks.t). Below, the stage-2 text.
 * R21 stage-2 load generator (R21 design §2.5): R16's HotGen unchanged plus mode quad (pk = global thread number mod 4; the
 * gate polls the same pk). Below, R16's text.
 * R16 stage-2 load generator (design §2.5): B18's HotGen plus the gate.
 * Driver 3.12.1 shaded from build/lib/jars, protocol V4, CL ONE, node at 127.0.0.1:9042.
 * usage: HotGen <nIPs> <threadsPerIP> <R> <hot|perthread|quad> <seconds> <statsfile> <stopfile> [rateMiBps] [--gate-selftest]
 * One request = an unlogged single-partition batch of R rows INSERT INTO ks.t (pk, ck, v), v = 8,192 random bytes from a pool of
 * 64 arrays, ck from a global counter. hot: pk = 1; perthread: pk = global thread number. One Cluster per source IP
 * 127.0.0.(11+i), bound through NettyOptions.afterBootstrapInitialized; one connection per Cluster, 2,048 requests max, read
 * timeout 30 s; synchronous, one request in flight per thread.
 * THE GATE (R16): after a WriteTimeoutException, a client-side OperationTimedOutException or any error other than
 * OverloadedException / NoHostAvailableException / TransportException, the thread sends no further write; it polls
 * SELECT ck FROM ks.t WHERE pk = ? AND ck = ? (CL ONE) for the LAST row of its timed-out batch every 500 ms until the row is
 * returned (the batch is one PartitionUpdate, applied atomically). Poll errors are counted and polling continues. After 120 s
 * without the row the thread retires (sends nothing more; counted). OverloadedException / NoHostAvailableException /
 * TransportException: sleep 1 s (nothing pending, or node gone).
 * --gate-selftest: every 10th success is treated as if it had timed out (Step A only, never in a reading).
 * Stats each second: ms,req_ok,rows_ok,err_wto,err_ovl,err_tra,err_nha,err_oth,connected,gated_now,gate_waits,
 * gate_wait_ms_total,gate_polls,gate_poll_err,retired.
 * Stops at <seconds>, at the stopfile, or after 60 s with no success and no connected host. rateMiBps (optional, 0 = none):
 * a global pacing of request starts so that values are sent at <= rateMiBps (Crm fallback, §2.7).
 */
public class HotGen
{
    static final int VB = 8192;

    public static void main(String[] a0) throws Exception
    {
        boolean st = false;
        java.util.List<String> al = new java.util.ArrayList<>();
        for (String s : a0) { if (s.equals("--gate-selftest")) st = true; else al.add(s); }
        final boolean selftest = st;
        final String[] a = al.toArray(new String[0]);
        final int nIPs = Integer.parseInt(a[0]);
        final int tpi = Integer.parseInt(a[1]);
        final int rows = Integer.parseInt(a[2]);
        final String mode = a[3];
        final int secs = Integer.parseInt(a[4]);
        final String stats = a[5];
        final File stop = new File(a[6]);
        final double rate = a.length > 7 ? Double.parseDouble(a[7]) : 0;
        if (!mode.equals("hot") && !mode.equals("perthread") && !mode.equals("quad"))
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
        final PreparedStatement[] sel = new PreparedStatement[nIPs];
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
                            .withCredentials(System.getenv("R21_USER"), System.getenv("R21_PASS"))   // 3-b: the attacker role
                            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(30_000).setConnectTimeoutMillis(30_000))
                            .build();
            ss[i] = cls[i].connect();
            ps[i] = ss[i].prepare("INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)");
            ps[i].setConsistencyLevel(ConsistencyLevel.ONE);
            sel[i] = ss[i].prepare("SELECT ck FROM ks.t WHERE pk = ? AND ck = ?");
            sel[i].setConsistencyLevel(ConsistencyLevel.ONE);
        }
        final AtomicLong ckc = new AtomicLong(), reqs = new AtomicLong(), rowsDone = new AtomicLong();
        final AtomicLong[] errs = new AtomicLong[5];
        for (int i = 0; i < 5; i++) errs[i] = new AtomicLong();
        final AtomicLong gatedNow = new AtomicLong(), gateWaits = new AtomicLong(), gateWaitMs = new AtomicLong(),
                         gatePolls = new AtomicLong(), gatePollErr = new AtomicLong(), retired = new AtomicLong(),
                         gateFirstPoll = new AtomicLong(), gateMaxPolls = new AtomicLong();
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
                long nOk = 0;
                while (System.currentTimeMillis() < end && !stop.exists() && !halt[0])
                {
                    int pk = mode.equals("perthread") ? id : mode.equals("quad") ? id % 4 : 1;
                    long base = -1;
                    boolean gate = false;
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
                        BatchStatement b = new BatchStatement(BatchStatement.Type.UNLOGGED);
                        base = ckc.getAndAdd(rows);
                        for (int i = 0; i < rows; i++)
                            b.add(ps[ip].bind(pk, (int) (base + i), pool[r.nextInt(pool.length)].duplicate()));
                        b.setConsistencyLevel(ConsistencyLevel.ONE);
                        ss[ip].execute(b);
                        reqs.incrementAndGet();
                        rowsDone.addAndGet(rows);
                        lastOk.set(System.currentTimeMillis());
                        nOk++;
                        if (selftest && nOk % 10 == 0)
                            gate = true;
                    }
                    catch (Throwable e)
                    {
                        int k = e instanceof WriteTimeoutException ? 0 : e instanceof OverloadedException ? 1
                              : e instanceof TransportException ? 2 : e instanceof NoHostAvailableException ? 3 : 4;
                        long n = errs[k].incrementAndGet();
                        if (n <= 10) { synchronized (ew) { ew.println(System.currentTimeMillis() + " " + e); ew.flush(); } }
                        if ((k == 0 || k == 4) && base >= 0)
                            gate = true;
                        else
                            try { Thread.sleep(1000); } catch (InterruptedException x) { }
                    }
                    if (gate)
                    {
                        // the gate: no new write until the last row of this batch is readable (or 120 s: retire)
                        gatedNow.incrementAndGet();
                        gateWaits.incrementAndGet();
                        long g0 = System.currentTimeMillis();
                        int polls = 0;
                        boolean found = false;
                        while (System.currentTimeMillis() - g0 < 120_000)
                        {
                            polls++;
                            gatePolls.incrementAndGet();
                            try
                            {
                                ResultSet rs = ss[ip].execute(sel[ip].bind(pk, (int) (base + rows - 1)));
                                if (rs.one() != null) { found = true; break; }
                            }
                            catch (Throwable pe)
                            {
                                long n = gatePollErr.incrementAndGet();
                                if (n <= 5) { synchronized (ew) { ew.println(System.currentTimeMillis() + " poll " + pe); ew.flush(); } }
                            }
                            try { Thread.sleep(500); } catch (InterruptedException x) { }
                        }
                        gatedNow.decrementAndGet();
                        gateWaitMs.addAndGet(System.currentTimeMillis() - g0);
                        if (found && polls == 1) gateFirstPoll.incrementAndGet();
                        synchronized (gateMaxPolls) { if (polls > gateMaxPolls.get()) gateMaxPolls.set(polls); }
                        if (!found)
                        {
                            retired.incrementAndGet();
                            synchronized (ew) { ew.println(System.currentTimeMillis() + " retired thread " + id + " pk " + pk + " ck " + (base + rows - 1)); ew.flush(); }
                            return;
                        }
                    }
                }
            });
            ts[t].start();
        }
        if (reqNanosAtRate == 0) nextStart.set(0);
        String why = "end";
        try (PrintWriter w = new PrintWriter(new FileWriter(stats)))
        {
            w.println("ms,req_ok,rows_ok,err_wto,err_ovl,err_tra,err_nha,err_oth,connected,gated_now,gate_waits,gate_wait_ms_total,gate_polls,gate_poll_err,retired");
            while (true)
            {
                boolean alive = false;
                for (Thread t : ts) alive |= t.isAlive();
                int conn = 0;
                for (Session s : ss)
                    if (!s.getState().getConnectedHosts().isEmpty()) conn++;
                long now = System.currentTimeMillis();
                w.println(now + "," + reqs.get() + "," + rowsDone.get() + "," + errs[0].get() + "," + errs[1].get() + ","
                          + errs[2].get() + "," + errs[3].get() + "," + errs[4].get() + "," + conn + "," + gatedNow.get() + ","
                          + gateWaits.get() + "," + gateWaitMs.get() + "," + gatePolls.get() + "," + gatePollErr.get() + ","
                          + retired.get());
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
                           + ",\"errors\":" + e + ",\"payload_bytes\":" + rowsDone.get() * (long) VB + ",\"gate_waits\":" + gateWaits.get()
                           + ",\"gate_first_poll\":" + gateFirstPoll.get() + ",\"gate_max_polls\":" + gateMaxPolls.get()
                           + ",\"gate_polls\":" + gatePolls.get() + ",\"retired\":" + retired.get() + ",\"selftest\":" + selftest + "}");
        System.out.flush();
        ew.close();
        // closing the clusters can hang when the node is gone; exit directly
        System.exit(0);
    }
}
