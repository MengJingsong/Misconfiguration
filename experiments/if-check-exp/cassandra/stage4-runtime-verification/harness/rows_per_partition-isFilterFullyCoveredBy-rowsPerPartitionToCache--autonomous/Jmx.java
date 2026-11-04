import javax.management.*;
import javax.management.remote.*;
import java.io.*;

/** Row-cache gauge and table-counter reader. Usage: java Jmx <jmx-port> once <table> | poll <interval-ms> <outfile> <table>
 *  Prints "epoch_ms,size,capacity,entries,hit,miss,outOfRange": gauges org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Capacity|Entries
 *  (attribute Value) and table counters type=Table,keyspace=ks,scope=<table>,name=RowCacheHit|RowCacheMiss|RowCacheHitOutOfRange (attribute Count). */
public class Jmx
{
    static Object g(MBeanServerConnection c, String n, String attr) throws Exception
    {
        return c.getAttribute(new ObjectName(n), attr);
    }
    static String line(MBeanServerConnection c, String table) throws Exception
    {
        long t = System.currentTimeMillis();
        String cp = "org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=";
        String tp = "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=" + table + ",name=";
        return t + "," + g(c, cp + "Size", "Value") + "," + g(c, cp + "Capacity", "Value") + "," + g(c, cp + "Entries", "Value") + ","
               + g(c, tp + "RowCacheHit", "Count") + "," + g(c, tp + "RowCacheMiss", "Count") + "," + g(c, tp + "RowCacheHitOutOfRange", "Count");
    }
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            if (a[1].equals("once")) { System.out.println(line(c, a[2])); return; }
            long iv = Long.parseLong(a[2]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[3])))
            {
                w.println("epoch_ms,size,capacity,entries,hit,miss,outOfRange");
                while (true) { try { w.println(line(c, a[4])); w.flush(); } catch (Exception ex) { w.println("ERR," + ex); w.flush(); return; } Thread.sleep(iv); }
            }
        }
    }
}
