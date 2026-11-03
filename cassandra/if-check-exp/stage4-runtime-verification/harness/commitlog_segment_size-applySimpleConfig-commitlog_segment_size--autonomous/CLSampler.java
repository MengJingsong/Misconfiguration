import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.Attribute;
import javax.management.AttributeList;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous.
 * Pattern of harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/ISSampler.java (one JMX connection;
 * jstat cannot attach here). Modes:
 *   sample <port> <csv> <intervalMs> <stopfile>  appends every interval, until <stopfile> is removed:
 *     ts_ms,total_commitlog_size,oversized_count,mapped_count,mapped_capacity,mapped_used,heap_used
 *     (org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize Value / name=OverSizedMutations Count;
 *      java.nio:type=BufferPool,name=mapped Count,TotalCapacity,MemoryUsed read in one getAttributes call; java.lang:type=Memory)
 *   once <port>                                   prints one such line (read-back).
 */
public class CLSampler
{
    static final ObjectName TOTAL, OVER, MAPPED, MEM;
    static
    {
        try
        {
            TOTAL = new ObjectName("org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize");
            OVER = new ObjectName("org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations");
            MAPPED = new ObjectName("java.nio:type=BufferPool,name=mapped");
            MEM = new ObjectName("java.lang:type=Memory");
        }
        catch (Exception e)
        {
            throw new RuntimeException(e);
        }
    }

    static String line(MBeanServerConnection m) throws Exception
    {
        long t = System.currentTimeMillis();
        Object total = m.getAttribute(TOTAL, "Value");
        Object over = m.getAttribute(OVER, "Count");
        AttributeList al = m.getAttributes(MAPPED, new String[]{ "Count", "TotalCapacity", "MemoryUsed" });
        long[] v = new long[3];
        for (Object o : al)
        {
            Attribute a = (Attribute) o;
            long x = ((Number) a.getValue()).longValue();
            if (a.getName().equals("Count")) v[0] = x;
            else if (a.getName().equals("TotalCapacity")) v[1] = x;
            else v[2] = x;
        }
        long heap = (Long) ((CompositeData) m.getAttribute(MEM, "HeapMemoryUsage")).get("used");
        return t + "," + total + "," + over + "," + v[0] + "," + v[1] + "," + v[2] + "," + heap;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("once"))
            {
                System.out.println("CL ts_ms,total_commitlog_size,oversized_count,mapped_count,mapped_capacity,mapped_used,heap_used");
                System.out.println("CL " + line(m));
                return;
            }
            long iv = Long.parseLong(a[3]);
            File stop = new File(a[4]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[2], true)))
            {
                w.println("ts_ms,total_commitlog_size,oversized_count,mapped_count,mapped_capacity,mapped_used,heap_used");
                while (stop.exists())
                {
                    long t0 = System.currentTimeMillis();
                    try
                    {
                        w.println(line(m));
                    }
                    catch (Exception e)
                    {
                        w.println("# error " + t0 + " " + e);
                    }
                    w.flush();
                    long s = iv - (System.currentTimeMillis() - t0);
                    if (s > 0) Thread.sleep(s);
                }
            }
        }
    }
}
