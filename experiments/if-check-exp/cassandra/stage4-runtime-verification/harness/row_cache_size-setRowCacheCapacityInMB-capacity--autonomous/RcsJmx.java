import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-26) of row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.
 * usage: java RcsJmx poll <csv> <stopfile> <pid>   every 2 s append
 *            epoch_ms,size,entries,capacity,hits,misses,requests,tbl_miss,tbl_hit,rss_kib   until <stopfile> exists
 *        java RcsJmx get                           one line: size=.. entries=.. capacity=..
 *        java RcsJmx neg                           set CacheService attribute RowCacheCapacityInMB = -1 (calls setRowCacheCapacityInMB(-1)); print the outcome and the capacity after
 *        java RcsJmx ledger                        (cluster re-run, 2026-10-27) one line: size, entries, capacity and every attribute of the
 *                                                  ledger MBean stage4:type=RcsLedger (RcsLedger.java), then the live-block histogram
 * Cluster re-run (2026-10-27): poll appends the ledger columns after rss_kib (the first ten columns are as in run 1);
 * a column reads ERR:<exception> if the MBean is absent (run 1, or a node without the agent).
 * JMX at 127.0.0.1:7199. (Pattern from the memtable_offheap_space harness's Sampler.java.)
 */
public class RcsJmx
{
    static final String RC = "org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=";
    static final String TB = "org.apache.cassandra.metrics:type=Table,keyspace=keyspace1,scope=standard1,name=";
    static final String LG = "stage4:type=RcsLedger";
    static final String[] LA = { "EntryBlocks", "EntryBytes", "EntryMalloc", "TableBlocks", "TableBytes", "TableMalloc",
                                 "UnknownFrees", "DuplicateAllocs", "MallocSizeErrors", "EntryMaxBytes", "Allocs", "Frees" };

    static String ledgerCsv(MBeanServerConnection m)
    {
        StringBuilder sb = new StringBuilder();
        for (String x : LA)
            sb.append(',').append(attr(m, LG, x));
        return sb.toString();
    }

    static Object attr(MBeanServerConnection m, String on, String a)
    {
        try
        {
            return m.getAttribute(new ObjectName(on), a);
        }
        catch (Exception e)
        {
            return "ERR:" + e.getClass().getSimpleName();
        }
    }

    static String rss(String pid)
    {
        try
        {
            Process p = new ProcessBuilder("ps", "-o", "rss=", "-p", pid).redirectErrorStream(true).start();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream())))
            {
                String l = r.readLine();
                p.waitFor();
                return l == null ? "" : l.trim();
            }
        }
        catch (Exception e)
        {
            return "ERR";
        }
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("get"))
            {
                System.out.println("size=" + attr(m, RC + "Size", "Value") + " entries=" + attr(m, RC + "Entries", "Value")
                                   + " capacity=" + attr(m, RC + "Capacity", "Value"));
                return;
            }
            if (a[0].equals("ledger"))
            {
                StringBuilder sb = new StringBuilder("epoch_ms=" + System.currentTimeMillis() + " size=" + attr(m, RC + "Size", "Value") + " entries=" + attr(m, RC + "Entries", "Value")
                                                     + " capacity=" + attr(m, RC + "Capacity", "Value"));
                for (String x : LA)
                    sb.append(' ').append(x).append('=').append(attr(m, LG, x));
                System.out.println(sb);
                System.out.println("histogram=" + attr(m, LG, "Histogram"));
                return;
            }
            if (a[0].equals("neg"))
            {
                System.out.println("capacity_before=" + attr(m, RC + "Capacity", "Value"));
                try
                {
                    // a void one-argument "set" method of a standard MBean is a (write-only) attribute, not an operation
                    m.setAttribute(new ObjectName("org.apache.cassandra.db:type=Caches"), new javax.management.Attribute("RowCacheCapacityInMB", -1L));
                    System.out.println("neg threw=none");
                }
                catch (Exception e)
                {
                    StringBuilder sb = new StringBuilder();
                    for (Throwable t = e; t != null; t = t.getCause())
                        sb.append(" | ").append(t.getClass().getName()).append(": ").append(t.getMessage());
                    System.out.println("neg threw=" + e.getClass().getName() + " chain=" + sb);
                }
                System.out.println("capacity_after=" + attr(m, RC + "Capacity", "Value"));
                return;
            }
            File stop = new File(a[2]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[1], true), true))
            {
                StringBuilder hd = new StringBuilder("epoch_ms,size,entries,capacity,hits,misses,requests,tbl_miss,tbl_hit,rss_kib");
                for (String x : LA)
                    hd.append(",l_").append(x);
                w.println(hd);
                long next = System.currentTimeMillis();
                while (true)
                {
                    boolean last = stop.exists();
                    long t = System.currentTimeMillis();
                    w.println(t + "," + attr(m, RC + "Size", "Value") + "," + attr(m, RC + "Entries", "Value") + ","
                              + attr(m, RC + "Capacity", "Value") + "," + attr(m, RC + "Hits", "Count") + ","
                              + attr(m, RC + "Misses", "Count") + "," + attr(m, RC + "Requests", "Count") + ","
                              + attr(m, TB + "RowCacheMiss", "Count") + "," + attr(m, TB + "RowCacheHit", "Count") + ","
                              + rss(a[3]) + ledgerCsv(m));
                    if (last)
                        break;
                    next += 2000;
                    long sl = next - System.currentTimeMillis();
                    if (sl > 0)
                        Thread.sleep(sl);
                }
            }
        }
    }
}
