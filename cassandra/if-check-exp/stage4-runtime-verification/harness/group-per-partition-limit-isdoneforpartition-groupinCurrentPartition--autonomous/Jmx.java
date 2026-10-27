import javax.management.*;
import javax.management.openmbean.CompositeData;
import javax.management.remote.*;
import java.io.*;
import java.util.*;

/** Heap sampler. Usage: java Jmx <jmx-port> once | poll <interval-ms> <outfile>
 *  Line: epoch_ms,heap_used,pools_collection_used,alloc_all_threads
 *   heap_used            java.lang:type=Memory HeapMemoryUsage.used
 *   pools_collection_used sum of CollectionUsage.used over the heap memory pools (live heap as of each pool's last collection)
 *   alloc_all_threads    sum of getThreadAllocatedBytes over the live threads (monotone except for exited threads) */
public class Jmx
{
    static long line(MBeanServerConnection c, PrintWriter w, List<ObjectName> pools) throws Exception
    {
        long t = System.currentTimeMillis();
        CompositeData hu = (CompositeData) c.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage");
        long used = (Long) hu.get("used"), coll = 0;
        for (ObjectName p : pools)
        {
            Object cu = c.getAttribute(p, "CollectionUsage");
            if (cu != null) coll += (Long) ((CompositeData) cu).get("used");
        }
        ObjectName th = new ObjectName("java.lang:type=Threading");
        long[] ids = (long[]) c.getAttribute(th, "AllThreadIds");
        long[] al = (long[]) c.invoke(th, "getThreadAllocatedBytes", new Object[]{ ids }, new String[]{ "[J" });
        long sum = 0; for (long x : al) if (x > 0) sum += x;
        String s = t + "," + used + "," + coll + "," + sum;
        if (w != null) { w.println(s); w.flush(); } else System.out.println(s);
        return t;
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            List<ObjectName> pools = new ArrayList<>();
            for (ObjectName n : c.queryNames(new ObjectName("java.lang:type=MemoryPool,*"), null))
                if ("HEAP".equals(String.valueOf(c.getAttribute(n, "Type")))) pools.add(n);
            if (a[1].equals("once")) { line(c, null, pools); return; }
            long iv = Long.parseLong(a[2]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[3])))
            {
                w.println("epoch_ms,heap_used,pools_collection_used,alloc_all_threads");
                while (true) { try { line(c, w, pools); } catch (Exception ex) { w.println("ERR," + ex); w.flush(); return; } Thread.sleep(iv); }
            }
        }
    }
}
