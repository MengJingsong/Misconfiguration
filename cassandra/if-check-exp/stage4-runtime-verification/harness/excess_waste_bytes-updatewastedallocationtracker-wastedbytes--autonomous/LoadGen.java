import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

import com.datastax.driver.core.BatchStatement;
import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.ConsistencyLevel;
import com.datastax.driver.core.HostDistance;
import com.datastax.driver.core.PoolingOptions;
import com.datastax.driver.core.PreparedStatement;
import com.datastax.driver.core.ProtocolVersion;
import com.datastax.driver.core.Session;
import com.datastax.driver.core.SocketOptions;

/**
 * Stage-4 load generator for the EXCESS_WASTE_* cluster tiers (written 2026-10-28), cassandra-driver 3.12.1 from the build, protocol V4.
 * usage: LoadGen <host> <threads> <seconds> <pkmode> <rowsPerBatch> <valueBytes> <stopfile> <statsfile> [maxPayloadMiB]
 *   pkmode: hot        pk = 1 for every request, ck = a global counter (new row every time)
 *           hotrand    pk = 1, ck random in [0, 10,000,000) (case EXCESS_WASTE_BYTES-wastedbytes B3c)
 *           cold       pk random in [0, 1,000,000), ck = a global counter
 *           perthread  pk = thread number, ck = a global counter
 * One request = an unlogged batch of rowsPerBatch inserts (a plain insert when 1) into ks.t(pk int, ck int, v blob), consistency ONE.
 * Writes "<epoch ms>,<requests>,<rows>,<errors>" to statsfile each second; stops at <seconds>, at the stopfile, or after maxPayloadMiB of payload.
 */
public class LoadGen
{
    public static void main(String[] a) throws Exception
    {
        String host = a[0];
        int threads = Integer.parseInt(a[1]);
        int secs = Integer.parseInt(a[2]);
        String mode = a[3];
        int rows = Integer.parseInt(a[4]);
        int vb = Integer.parseInt(a[5]);
        File stop = new File(a[6]);
        long maxPayload = (a.length > 8 ? Long.parseLong(a[8]) : 1_000_000L) << 20;
        PoolingOptions po = new PoolingOptions().setConnectionsPerHost(HostDistance.LOCAL, 4, 4).setMaxRequestsPerConnection(HostDistance.LOCAL, 2048);
        Cluster cl = Cluster.builder().addContactPoint(host).withProtocolVersion(ProtocolVersion.V4).withPoolingOptions(po)
                            .withSocketOptions(new SocketOptions().setReadTimeoutMillis(300_000).setConnectTimeoutMillis(30_000)).build();
        Session s = cl.connect();
        PreparedStatement ps = s.prepare("INSERT INTO ks.t (pk, ck, v) VALUES (?, ?, ?)");
        ps.setConsistencyLevel(ConsistencyLevel.ONE);
        // a pool of different random values (about 256 KiB in all) so that the SSTables are not compressed to nothing
        final ByteBuffer[] pool = new ByteBuffer[Math.max(1, Math.min(1024, (256 * 1024) / Math.max(1, vb)))];
        for (int i = 0; i < pool.length; i++)
        {
            byte[] b = new byte[vb];
            ThreadLocalRandom.current().nextBytes(b);
            pool[i] = ByteBuffer.wrap(b);
        }
        final AtomicLong ckc = new AtomicLong(), reqs = new AtomicLong(), rowsDone = new AtomicLong(), errs = new AtomicLong();
        final long end = System.currentTimeMillis() + secs * 1000L;
        final PrintWriter ew = new PrintWriter(new FileWriter(a[7] + ".errors"));
        Thread[] ts = new Thread[threads];
        for (int t = 0; t < threads; t++)
        {
            final int id = t;
            ts[t] = new Thread(() -> {
                ThreadLocalRandom r = ThreadLocalRandom.current();
                while (System.currentTimeMillis() < end && !stop.exists() && rowsDone.get() * (long) vb < maxPayload)
                {
                    try
                    {
                        int pk = mode.equals("perthread") ? id : mode.equals("cold") ? r.nextInt(1_000_000) : 1;
                        if (rows == 1)
                        {
                            int ck = mode.equals("hotrand") ? r.nextInt(10_000_000) : (int) ckc.getAndIncrement();
                            s.execute(ps.bind(pk, ck, pool[r.nextInt(pool.length)].duplicate()));
                        }
                        else
                        {
                            BatchStatement b = new BatchStatement(BatchStatement.Type.UNLOGGED);
                            long base = ckc.getAndAdd(rows);
                            for (int i = 0; i < rows; i++)
                                b.add(ps.bind(pk, (int) (base + i), pool[r.nextInt(pool.length)].duplicate()));
                            b.setConsistencyLevel(ConsistencyLevel.ONE);
                            s.execute(b);
                        }
                        reqs.incrementAndGet();
                        rowsDone.addAndGet(rows);
                    }
                    catch (Throwable e)
                    {
                        if (errs.incrementAndGet() <= 20) { ew.println(System.currentTimeMillis() + " " + e); ew.flush(); }
                        try { Thread.sleep(50); } catch (InterruptedException x) { }
                    }
                }
            });
            ts[t].start();
        }
        try (PrintWriter w = new PrintWriter(new FileWriter(a[7])))
        {
            while (true)
            {
                boolean alive = false;
                for (Thread t : ts) alive |= t.isAlive();
                w.println(System.currentTimeMillis() + "," + reqs.get() + "," + rowsDone.get() + "," + errs.get());
                w.flush();
                if (!alive) break;
                Thread.sleep(1000);
            }
        }
        System.out.println("LOADGEN-DONE requests=" + reqs.get() + " rows=" + rowsDone.get() + " errors=" + errs.get() + " payloadBytes=" + rowsDone.get() * (long) vb);
        ew.close();
        cl.close();
        System.exit(0);
    }
}
