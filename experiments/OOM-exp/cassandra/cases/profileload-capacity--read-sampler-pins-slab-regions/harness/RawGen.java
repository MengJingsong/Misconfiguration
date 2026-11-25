import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

import com.datastax.driver.core.BoundStatement;
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
import com.datastax.driver.core.exceptions.OperationTimedOutException;
import com.datastax.driver.core.exceptions.OverloadedException;
import com.datastax.driver.core.exceptions.ReadTimeoutException;
import com.datastax.driver.core.exceptions.TransportException;
import com.datastax.driver.core.exceptions.WriteTimeoutException;
import com.datastax.shaded.netty.bootstrap.Bootstrap;

/**
 * B25 stage-2 read-after-write client (design §2.5). Driver 3.12.1 shaded from build/lib/jars, protocol V4, CL ONE, node at
 * 127.0.0.1:9042, source address 127.0.0.11 (bound through NettyOptions.afterBootstrapInitialized), one connection.
 * usage: RawGen <controlfile> <statsfile> <stopfile> <ratePerSec> <cells> <threadsPerTable> <maxSeconds>
 * The control file holds the hot table name (e.g. t3); it is re-read every 100 ms and the writer threads switch on change.
 * Each writer thread, serially: INSERT INTO b25.<hot> (pk, v0..v8) VALUES (?, ...) with pk = "k<k>-<thread>-<seq>" (k = table
 * suffix) and 9 values of 122,880 random bytes (from a pre-generated pool of 64 arrays); cells = 18 (fallback F1 only) sends two
 * such INSERTs to the same pk (2.1 MiB of slab allocation per key); then SELECT pk FROM b25.<hot> WHERE pk = ? and counts the rows.
 * Global pacing: request-pair starts at <= ratePerSec (one shared slot clock). Stats each second (statsfile):
 * ms,hot,ins_ok,reads_ok,reads_1row,err_wto,err_rto,err_ovl,err_tra,err_nha,err_oth,cyc_p50_ms,cyc_p99_ms,connected.
 * Per read (statsfile + ".reads"): ms,table,rows. Stops at <maxSeconds>, at the stopfile, or after 60 s with no success.
 */
public class RawGen
{
    static final int VB = 122_880;

    public static void main(String[] a) throws Exception
    {
        final File control = new File(a[0]);
        final String stats = a[1];
        final File stop = new File(a[2]);
        final double rate = Double.parseDouble(a[3]);
        final int cells = Integer.parseInt(a[4]);
        final int threads = Integer.parseInt(a[5]);
        final int secs = Integer.parseInt(a[6]);
        if (cells != 9 && cells != 18)
            throw new IllegalArgumentException("cells must be 9 or 18");
        final ByteBuffer[] pool = new ByteBuffer[64];
        Random rnd = new Random(25);
        for (int i = 0; i < pool.length; i++)
        {
            byte[] b = new byte[VB];
            rnd.nextBytes(b);
            pool[i] = ByteBuffer.wrap(b);
        }
        NettyOptions no = new NettyOptions()
        {
            @Override
            public void afterBootstrapInitialized(Bootstrap b)
            {
                b.localAddress(new InetSocketAddress("127.0.0.11", 0));
            }
        };
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 1, 1)
                                                .setMaxRequestsPerConnection(HostDistance.LOCAL, 2048);
        final Cluster cl = Cluster.builder().addContactPoint("127.0.0.1").withPort(9042).withProtocolVersion(ProtocolVersion.V4)
                                  .withPoolingOptions(po).withNettyOptions(no)
                                  .withSocketOptions(new SocketOptions().setReadTimeoutMillis(30_000).setConnectTimeoutMillis(30_000))
                                  .build();
        final Session s = cl.connect();
        final Map<String, PreparedStatement[]> prepared = new HashMap<>();
        final String[] hot = { readControl(control) };
        final AtomicLong ins = new AtomicLong(), rd = new AtomicLong(), rd1 = new AtomicLong();
        final AtomicLong[] errs = new AtomicLong[6];
        for (int i = 0; i < errs.length; i++) errs[i] = new AtomicLong();
        final AtomicLong lastOk = new AtomicLong(System.currentTimeMillis());
        final AtomicLong nextStart = new AtomicLong(System.nanoTime());
        final long slotNanos = (long) (1e9 / rate);
        final long end = System.currentTimeMillis() + secs * 1000L;
        final boolean[] halt = new boolean[1];
        final PrintWriter rw = new PrintWriter(new FileWriter(stats + ".reads"));
        final PrintWriter ew = new PrintWriter(new FileWriter(stats + ".errors"));
        final long[] lat = new long[100_000];
        final int[] nlat = new int[1];
        Thread ctl = new Thread(() -> {
            while (!halt[0])
            {
                try { String h = readControl(control); if (h != null && !h.isEmpty()) synchronized (hot) { hot[0] = h; } } catch (Exception e) { }
                try { Thread.sleep(100); } catch (InterruptedException e) { return; }
            }
        });
        ctl.setDaemon(true);
        ctl.start();
        Thread[] ts = new Thread[threads];
        for (int t = 0; t < threads; t++)
        {
            final int id = t;
            ts[t] = new Thread(() -> {
                ThreadLocalRandom r = ThreadLocalRandom.current();
                long seq = 0;
                while (System.currentTimeMillis() < end && !stop.exists() && !halt[0])
                {
                    String table;
                    synchronized (hot) { table = hot[0]; }
                    try
                    {
                        long slot;
                        synchronized (nextStart)
                        {
                            long now = System.nanoTime();
                            slot = Math.max(now, nextStart.get());
                            nextStart.set(slot + slotNanos);
                        }
                        long w = slot - System.nanoTime();
                        if (w > 0) Thread.sleep(w / 1_000_000, (int) (w % 1_000_000));
                        PreparedStatement[] ps;
                        synchronized (prepared)
                        {
                            ps = prepared.get(table);
                            if (ps == null)
                            {
                                ps = new PreparedStatement[]{
                                    s.prepare("INSERT INTO b25." + table + " (pk, v0, v1, v2, v3, v4, v5, v6, v7, v8) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
                                    s.prepare("SELECT pk FROM b25." + table + " WHERE pk = ?") };
                                ps[0].setConsistencyLevel(ConsistencyLevel.ONE);
                                ps[1].setConsistencyLevel(ConsistencyLevel.ONE);
                                prepared.put(table, ps);
                            }
                        }
                        String pk = "k" + table.substring(1) + "-" + id + "-" + (seq++);
                        long t0 = System.nanoTime();
                        for (int part = 0; part < cells / 9; part++)
                        {
                            Object[] vals = new Object[10];
                            vals[0] = pk;
                            for (int c = 0; c < 9; c++) vals[1 + c] = pool[r.nextInt(pool.length)].duplicate();
                            s.execute(ps[0].bind(vals));
                        }
                        ins.incrementAndGet();
                        ResultSet rs = s.execute(ps[1].bind(pk));
                        int rows = rs.all().size();
                        long t1 = System.nanoTime();
                        rd.incrementAndGet();
                        if (rows == 1) rd1.incrementAndGet();
                        long ms = System.currentTimeMillis();
                        synchronized (rw) { rw.println(ms + "," + table + "," + rows); }
                        synchronized (lat) { if (nlat[0] < lat.length) lat[nlat[0]++] = (t1 - t0) / 1000; }
                        lastOk.set(ms);
                    }
                    catch (Throwable e)
                    {
                        int k = e instanceof WriteTimeoutException ? 0 : e instanceof ReadTimeoutException ? 1
                              : e instanceof OverloadedException ? 2 : (e instanceof TransportException || e instanceof OperationTimedOutException) ? 3
                              : e instanceof NoHostAvailableException ? 4 : 5;
                        errs[k].incrementAndGet();
                        synchronized (ew) { ew.println(System.currentTimeMillis() + " " + table + " " + e); ew.flush(); }
                        if (k >= 2) { try { Thread.sleep(1000); } catch (InterruptedException ie) { return; } }
                    }
                }
            });
            ts[t].start();
        }
        PrintWriter pw = new PrintWriter(new FileWriter(stats));
        pw.println("ms,hot,ins_ok,reads_ok,reads_1row,err_wto,err_rto,err_ovl,err_tra,err_nha,err_oth,cyc_p50_ms,cyc_p99_ms,connected");
        pw.flush();
        while (true)
        {
            Thread.sleep(1000);
            boolean alive = false;
            for (Thread t : ts) alive |= t.isAlive();
            long[] l;
            synchronized (lat) { l = Arrays.copyOf(lat, nlat[0]); nlat[0] = 0; }
            Arrays.sort(l);
            String p50 = l.length > 0 ? String.format("%.1f", l[l.length / 2] / 1000.0) : "";
            String p99 = l.length > 0 ? String.format("%.1f", l[Math.min(l.length - 1, (int) (l.length * 0.99))] / 1000.0) : "";
            int conn = 0;
            try { conn = cl.getMetrics().getConnectedToHosts().getValue(); } catch (Exception e) { }
            String h;
            synchronized (hot) { h = hot[0]; }
            pw.println(System.currentTimeMillis() + "," + h + "," + ins.get() + "," + rd.get() + "," + rd1.get() + "," + errs[0].get() + ","
                       + errs[1].get() + "," + errs[2].get() + "," + errs[3].get() + "," + errs[4].get() + "," + errs[5].get() + ","
                       + p50 + "," + p99 + "," + conn);
            pw.flush();
            synchronized (rw) { rw.flush(); }
            if (!alive) break;
            if (System.currentTimeMillis() - lastOk.get() > 60_000 && conn == 0) { halt[0] = true; }
        }
        halt[0] = true;
        pw.close();
        synchronized (rw) { rw.close(); }
        ew.close();
        try { cl.close(); } catch (Exception e) { }
        System.exit(0);
    }

    static String readControl(File f) throws Exception
    {
        return new String(Files.readAllBytes(f.toPath())).trim();
    }
}
