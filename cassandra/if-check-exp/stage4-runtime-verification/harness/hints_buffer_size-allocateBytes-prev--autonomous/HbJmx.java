/*
 * Stage-4 harness, cluster tier (B3d, as amended 2026-10-26) of hints_buffer_size-allocateBytes-prev--autonomous.
 * A JMX sampler for node 1 (local JMX on 127.0.0.1:<port>, no auth). It replaces `nodetool sjk mx` (exits 0 on failure;
 * one JVM per call) and BSD-incompatible `du -sb`.
 *
 *   java HbJmx poll <port> <hintsDir> <out.tsv> <stopfile> <ms>
 *       every <ms>, one line: epoch_ms direct_used direct_count mapped_used total_hints hints_dir_bytes hints_files
 *         direct_*    java.nio:type=BufferPool,name=direct  MemoryUsed, Count (BufferPoolMXBean)
 *         mapped_used java.nio:type=BufferPool,name=mapped  MemoryUsed (commit log segments; reported only)
 *         total_hints org.apache.cassandra.metrics:type=Storage,name=TotalHints Count (StorageMetrics.totalHints,
 *                     incremented once per target host per hint, HintsService.java:171)
 *         hints_dir_bytes / hints_files: sum of file sizes / number of *.hints files under <hintsDir> (exact bytes)
 *       until <stopfile> exists. A failed sample is written as "<epoch_ms> ERR <message>" and polling goes on.
 *   java HbJmx once <port>   -> RESULT direct_used=.. direct_count=.. total_hints=..
 */
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class HbJmx
{
    static final String DIRECT = "java.nio:type=BufferPool,name=direct";
    static final String MAPPED = "java.nio:type=BufferPool,name=mapped";
    static final String HINTS = "org.apache.cassandra.metrics:type=Storage,name=TotalHints";

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[1] + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[0].equals("once"))
            {
                System.out.println("RESULT direct_used=" + num(m, DIRECT, "MemoryUsed") + " direct_count=" + num(m, DIRECT, "Count")
                                   + " total_hints=" + num(m, HINTS, "Count"));
                return;
            }
            File dir = new File(a[2]);
            File stop = new File(a[4]);
            long ms = Long.parseLong(a[5]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[3], true)))
            {
                w.println("# epoch_ms direct_used direct_count mapped_used total_hints hints_dir_bytes hints_files");
                w.flush();
                while (!stop.exists())
                {
                    long t = System.currentTimeMillis();
                    try
                    {
                        long du = num(m, DIRECT, "MemoryUsed"), dc = num(m, DIRECT, "Count"), mu = num(m, MAPPED, "MemoryUsed");
                        long th = num(m, HINTS, "Count");
                        long bytes = 0, files = 0;
                        File[] fs = dir.listFiles();
                        if (fs != null)
                            for (File f : fs)
                                if (f.isFile())
                                {
                                    bytes += f.length();
                                    if (f.getName().endsWith(".hints"))
                                        files++;
                                }
                        w.println(t + " " + du + " " + dc + " " + mu + " " + th + " " + bytes + " " + files);
                    }
                    catch (Exception e)
                    {
                        w.println(t + " ERR " + e.getClass().getSimpleName() + ":" + String.valueOf(e.getMessage()).replace(' ', '_'));
                    }
                    w.flush();
                    long sl = ms - (System.currentTimeMillis() - t);
                    if (sl > 0)
                        Thread.sleep(sl);
                }
            }
        }
    }

    static long num(MBeanServerConnection m, String name, String attr) throws Exception
    {
        ObjectName on = new ObjectName(name);
        if (!m.isRegistered(on))
            return -1;
        return ((Number) m.getAttribute(on, attr)).longValue();
    }
}
