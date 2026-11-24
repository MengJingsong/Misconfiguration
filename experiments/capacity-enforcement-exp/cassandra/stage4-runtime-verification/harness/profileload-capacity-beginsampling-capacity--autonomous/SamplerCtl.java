// $WORK/SamplerCtl.java
import javax.management.*; import javax.management.remote.*; import java.util.List;
public class SamplerCtl {
  public static void main(String[] a) throws Exception {
    try (JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"))) {
      MBeanServerConnection m = c.getMBeanServerConnection();
      ObjectName on = new ObjectName("org.apache.cassandra.db:type=Tables,keyspace=" + a[1] + ",table=" + a[2]);
      if (a[0].equals("begin"))
        m.invoke(on, "beginLocalSampling", new Object[]{ a[3], Integer.parseInt(a[4]), Integer.parseInt(a[5]) },
                 new String[]{ "java.lang.String", "int", "int" });
      else
        System.out.println("returned=" + ((List<?>) m.invoke(on, "finishLocalSampling", new Object[]{ a[3], Integer.parseInt(a[4]) },
                 new String[]{ "java.lang.String", "int" })).size());
    }
  }
}
