import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;

/** Allocation and heap sampler over JMX (no Cassandra classes). Not upstream code.
 *  Usage: java Jmx <jmx-port> once | poll <interval-ms> <outfile>
 *  A line is "epoch_ms,alloc_total,heap_used": alloc_total = sum over all live threads of ThreadMXBean.getThreadAllocatedBytes
 *  (java.lang:type=Threading, operation getThreadAllocatedBytes(long[])), heap_used = java.lang:type=Memory HeapMemoryUsage.used.
 *  Threads that die lose their count, so a window can read low; the analyzer takes the sample-to-sample deltas and reports negative windows. */
public class Jmx
{
    static String line(MBeanServerConnection c) throws Exception
    {
        ObjectName th = new ObjectName("java.lang:type=Threading");
        long t = System.currentTimeMillis();
        long[] ids = (long[]) c.getAttribute(th, "AllThreadIds");
        long[] al = (long[]) c.invoke(th, "getThreadAllocatedBytes", new Object[]{ ids }, new String[]{ "[J" });
        long sum = 0; for (long v : al) if (v > 0) sum += v;
        CompositeData hu = (CompositeData) c.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage");
        return t + "," + sum + "," + hu.get("used");
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            if (a[1].equals("once")) { System.out.println(line(c)); return; }
            long iv = Long.parseLong(a[2]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[3])))
            {
                w.println("epoch_ms,alloc_total,heap_used");
                while (true) { try { w.println(line(c)); w.flush(); } catch (Exception ex) { w.println("ERR," + ex); w.flush(); return; } Thread.sleep(iv); }
            }
        }
    }
}
