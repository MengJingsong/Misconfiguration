import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  switch (a[1]) {
    case "set": try { m.setAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), new Attribute("CompressedReadAheadBufferInKB", Integer.parseInt(a[2]))); System.out.println("OK " + a[2]); }
                catch (Exception e) { System.out.println("REJECTED " + a[2] + " " + e); }
                System.out.println("now " + m.getAttribute(new ObjectName("org.apache.cassandra.db:type=StorageService"), "CompressedReadAheadBufferInKB")); break;
    case "poll": ObjectName d = new ObjectName("java.nio:type=BufferPool,name=direct"); long end = System.currentTimeMillis() + Long.parseLong(a[2]) * 1000;
                while (System.currentTimeMillis() < end) { System.out.println(System.currentTimeMillis() + "," + m.getAttribute(d, "MemoryUsed") + "," + m.getAttribute(d, "Count")); Thread.sleep(100); } break;
  } } }
