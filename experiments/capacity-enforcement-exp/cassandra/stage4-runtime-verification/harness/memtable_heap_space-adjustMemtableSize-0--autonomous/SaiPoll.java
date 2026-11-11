// Charge sampler for the cluster tier (B3d, audit amendment A-K3) of memtable_heap_space-adjustMemtableSize-0--autonomous.
// Usage: java SaiPoll.java <jmx port> <table> <index or -> <period ms> <stop file>
// Prints one CSV line per period to stdout:
//   epoch_ms,ownsCur,allOwns,ops,switches,S,W,blocked,segBuf,heapUsed
// A value that cannot be read is printed as -1. Stops when the stop file exists or the JMX connection is lost 5 times in a row.
import java.io.File;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class SaiPoll
{
    static MBeanServerConnection c;

    static long get(String bean, String attr)
    {
        try
        {
            Object o = c.getAttribute(new ObjectName(bean), attr);
            return ((Number) o).longValue();
        }
        catch (Exception e)
        {
            return -1;
        }
    }

    public static void main(String[] a) throws Exception
    {
        int port = Integer.parseInt(a[0]);
        String table = a[1], index = a[2];
        long period = Long.parseLong(a[3]);
        File stop = new File(a[4]);
        String t = "org.apache.cassandra.metrics:type=Table,keyspace=saiks,scope=" + table + ",name=";
        String s = "org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=saiks,table=" + table + ",index=" + index + ",scope=IndexMetrics,name=";
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + port + "/jmxrmi");
        JMXConnector jc = JMXConnectorFactory.connect(url);
        c = jc.getMBeanServerConnection();
        System.out.println("epoch_ms,ownsCur,allOwns,ops,switches,S,W,blocked,segBuf,heapUsed");
        int fails = 0;
        while (!stop.exists())
        {
            long t0 = System.currentTimeMillis();
            long heap = -1;
            try
            {
                heap = ((Number) ((CompositeData) c.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")).get("used")).longValue();
                fails = 0;
            }
            catch (Exception e)
            {
                if (++fails >= 5) break;
            }
            boolean sai = !"-".equals(index);
            System.out.println(t0 + "," + get(t + "MemtableOnHeapDataSize", "Value") + "," + get(t + "AllMemtablesOnHeapDataSize", "Value")
                               + "," + get(t + "MemtableColumnsCount", "Value") + "," + get(t + "MemtableSwitchCount", "Count")
                               + "," + (sai ? get(s + "MemtableIndexBytes", "Value") : -1) + "," + (sai ? get(s + "LiveMemtableIndexWriteCount", "Value") : -1)
                               + "," + get("org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation", "Count")
                               + "," + get("org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes", "Value")
                               + "," + heap);
            System.out.flush();
            long sl = period - (System.currentTimeMillis() - t0);
            if (sl > 0) Thread.sleep(sl);
        }
        jc.close();
    }
}
