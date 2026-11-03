import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;

import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier B3d (amended 2026-10-25) of
 * compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous.
 * Modelled on harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/CounterCacheSampler.java
 * (one JMX connection; jstat cannot attach on this machine).
 *   java CrabJmx sample <port> <csv> <phasefile> <stopfile> <period_ms>
 *       appends epoch_ms,phase,direct_count,direct_used,direct_capacity,heap_used (java.nio:type=BufferPool,name=direct;
 *       java.lang:type=Memory) every period until <stopfile> exists (one last row after it appears).
 *   java CrabJmx get <port>             prints  GET CompressedReadAheadBufferInKB=<v>
 *   java CrabJmx set <port> <kib>       prints  SET <kib> OK  or  SET <kib> REJECTED <exception chain>, then the GET line
 */
public class CrabJmx
{
    static final String SS = "org.apache.cassandra.db:type=StorageService";
    static final String ATTR = "CompressedReadAheadBufferInKB";

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[1]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[0])
            {
                case "sample": sample(m, a[2], new File(a[3]), new File(a[4]), Long.parseLong(a[5])); break;
                case "get": get(m); break;
                case "set": set(m, Integer.parseInt(a[2])); get(m); break;
                default: throw new IllegalArgumentException(a[0]);
            }
        }
    }

    static void get(MBeanServerConnection m) throws Exception
    {
        System.out.println("GET " + ATTR + "=" + m.getAttribute(new ObjectName(SS), ATTR));
    }

    static void set(MBeanServerConnection m, int v)
    {
        try
        {
            m.setAttribute(new ObjectName(SS), new Attribute(ATTR, v));
            System.out.println("SET " + v + " OK");
        }
        catch (Throwable t)
        {
            StringBuilder b = new StringBuilder();
            for (Throwable x = t; x != null; x = x.getCause())
                b.append(b.length() == 0 ? "" : " <- ").append(x.getClass().getName()).append(": ").append(x.getMessage());
            System.out.println("SET " + v + " REJECTED " + b);
        }
    }

    static void sample(MBeanServerConnection m, String csv, File phase, File stop, long period) throws Exception
    {
        ObjectName direct = new ObjectName("java.nio:type=BufferPool,name=direct");
        ObjectName mem = new ObjectName("java.lang:type=Memory");
        try (PrintWriter w = new PrintWriter(new FileWriter(csv, true), true))
        {
            w.println("epoch_ms,phase,direct_count,direct_used,direct_capacity,heap_used");
            long next = System.currentTimeMillis();
            while (true)
            {
                boolean last = stop.exists();
                long t = System.currentTimeMillis();
                String ph = phase.exists() ? new String(Files.readAllBytes(phase.toPath())).trim() : "";
                String row;
                try
                {
                    row = t + "," + ph + "," + m.getAttribute(direct, "Count") + "," + m.getAttribute(direct, "MemoryUsed") + ","
                          + m.getAttribute(direct, "TotalCapacity") + "," + ((CompositeData) m.getAttribute(mem, "HeapMemoryUsage")).get("used");
                }
                catch (Exception e)
                {
                    row = t + "," + ph + ",ERROR " + e.getClass().getSimpleName() + ",,,";
                }
                w.println(row);
                if (last) break;
                next += period;
                long sl = next - System.currentTimeMillis();
                if (sl > 0) Thread.sleep(sl);
            }
        }
    }
}
