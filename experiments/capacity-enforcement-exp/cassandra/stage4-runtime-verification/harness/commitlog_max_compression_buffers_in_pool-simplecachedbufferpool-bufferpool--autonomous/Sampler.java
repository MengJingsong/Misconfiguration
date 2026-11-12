// Stage-4 harness (amendment M7): every 2 s, one CSV line
// epoch_ms,direct_used,direct_count,waits_count,segment_files
// read over JMX from the node (direct BufferPool MXBean; CommitLog WaitingOnSegmentAllocation Count) plus the commit-log file count.
// usage: java Sampler.java <jmx-port> <commitlog-dir> <out.csv> <stop-file>
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class Sampler
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        File cl = new File(a[1]);
        File stop = new File(a[3]);
        ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
        ObjectName waits = new ObjectName("org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation");
        try (JMXConnector c = JMXConnectorFactory.connect(url); PrintWriter out = new PrintWriter(new FileWriter(a[2], true)))
        {
            MBeanServerConnection s = c.getMBeanServerConnection();
            out.println("epoch_ms,direct_used,direct_count,waits_count,segment_files");
            long next = System.currentTimeMillis();
            while (!stop.exists())
            {
                long now = System.currentTimeMillis();
                String line;
                try
                {
                    File[] fs = cl.listFiles((d, n) -> n.endsWith(".log"));
                    line = now + "," + s.getAttribute(direct, "MemoryUsed") + "," + s.getAttribute(direct, "Count") + ","
                           + s.getAttribute(waits, "Count") + "," + (fs == null ? -1 : fs.length);
                }
                catch (Exception e)
                {
                    line = now + ",ERR,ERR,ERR,ERR " + e;
                }
                out.println(line);
                out.flush();
                next += 2000;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
