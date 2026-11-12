// Stage-4 harness (case ...-usedbuffers--autonomous, cluster tier B3d as amended by M6): JMX poller, JDK classes only.
// usage: java O45Jmx <jmx-port> <interval-ms>   -> CSV on stdout, one line per sample, until killed.
// Columns: epoch_ms, direct_used, direct_count, mapped_used, wosa_count (CommitLog WaitingOnSegmentAllocation Count),
//          woc_count (CommitLog WaitingOnCommit Count), bp_networking (BufferPool Size scope=networking),
//          bp_chunk (BufferPool Size scope=chunk-cache), heap_used. -1 = not readable at that sample.
import java.lang.management.MemoryUsage;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class O45Jmx
{
    static long num(MBeanServerConnection c, String bean, String attr)
    {
        try
        {
            Object o = c.getAttribute(new ObjectName(bean), attr);
            if (o instanceof CompositeData)
                return ((Number) ((CompositeData) o).get("used")).longValue();
            return ((Number) o).longValue();
        }
        catch (Exception e)
        {
            return -1;
        }
    }

    public static void main(String[] a) throws Exception
    {
        String port = a[0];
        long interval = Long.parseLong(a[1]);
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        System.out.println("epoch_ms,direct_used,direct_count,mapped_used,wosa_count,woc_count,bp_networking,bp_chunk,heap_used");
        JMXConnector jc = null;
        while (true)
        {
            long t = System.currentTimeMillis();
            try
            {
                if (jc == null)
                    jc = JMXConnectorFactory.connect(url);
                MBeanServerConnection c = jc.getMBeanServerConnection();
                String m = "org.apache.cassandra.metrics:";
                System.out.println(t + "," + num(c, "java.nio:type=BufferPool,name=direct", "MemoryUsed")
                                   + "," + num(c, "java.nio:type=BufferPool,name=direct", "Count")
                                   + "," + num(c, "java.nio:type=BufferPool,name=mapped", "MemoryUsed")
                                   + "," + num(c, m + "type=CommitLog,name=WaitingOnSegmentAllocation", "Count")
                                   + "," + num(c, m + "type=CommitLog,name=WaitingOnCommit", "Count")
                                   + "," + num(c, m + "type=BufferPool,name=Size,scope=networking", "Value")
                                   + "," + num(c, m + "type=BufferPool,name=Size,scope=chunk-cache", "Value")
                                   + "," + num(c, "java.lang:type=Memory", "HeapMemoryUsage"));
            }
            catch (Exception e)
            {
                System.out.println("# " + t + " jmx error " + e);
                try { if (jc != null) jc.close(); } catch (Exception ignore) {}
                jc = null;
            }
            System.out.flush();
            long sleep = t + interval - System.currentTimeMillis();
            if (sleep > 0)
                Thread.sleep(sleep);
        }
    }
}
