import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.
 * Copied from harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/CLSampler.java, then changed
 * (attributes). One JMX connection (jstat cannot attach here; nodetool sjk can exit 0 on failure). Modes:
 *   once <port>                                  prints a header and one line
 *   sample <port> <csv> <intervalMs> <stopfile>  appends a line every interval until <stopfile> is removed
 * Line: ts_ms,oversized_count,active_content_size,total_commitlog_size,heap_used
 *   org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations Count (CommitLogMetrics.java:55)
 *   org.apache.cassandra.db:type=Commitlog ActiveContentSize (CommitLogMBean.java:80, CommitLog.java:430-436)
 *   org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize Value; java.lang:type=Memory heap used
 */
public class MMSampler
{
    static final ObjectName OVER, CL, TOTAL, MEM;
    static
    {
        try
        {
            OVER = new ObjectName("org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations");
            CL = new ObjectName("org.apache.cassandra.db:type=Commitlog");
            TOTAL = new ObjectName("org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize");
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
        Object over = m.getAttribute(OVER, "Count");
        Object content = m.getAttribute(CL, "ActiveContentSize");
        Object total = m.getAttribute(TOTAL, "Value");
        long heap = (Long) ((CompositeData) m.getAttribute(MEM, "HeapMemoryUsage")).get("used");
        return t + "," + over + "," + content + "," + total + "," + heap;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("once"))
            {
                System.out.println("MM ts_ms,oversized_count,active_content_size,total_commitlog_size,heap_used");
                System.out.println("MM " + line(m));
                return;
            }
            long iv = Long.parseLong(a[3]);
            File stop = new File(a[4]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[2], true)))
            {
                w.println("ts_ms,oversized_count,active_content_size,total_commitlog_size,heap_used");
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
