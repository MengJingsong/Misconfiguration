import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Rep { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService"); int n = Integer.parseInt(a[1]);
  for (int i = 0; i < n; i++) { m.invoke(ss, "repairAsync", new Object[]{"rs", new HashMap<String, String>()}, new String[]{"java.lang.String", "java.util.Map"}); if (i % 50 == 49) Thread.sleep(1000); }
  System.out.println("issued " + n); } }
