// Stage-4 harness helper: keeps one JMX connection open and, on the lines "enable" and "disable" on stdin, calls
// StorageService.enableAutoCompaction / disableAutoCompaction(ks, table) at once (a nodetool JVM needs about 2 s, longer than a small first task).
// usage: java LcDisable <jmx port> <keyspace> <table>
import javax.management.*;
import javax.management.remote.*;
import java.io.*;

public class LcDisable
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        JMXConnector c = JMXConnectorFactory.connect(u);
        MBeanServerConnection m = c.getMBeanServerConnection();
        ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
        System.out.println("ready"); System.out.flush();
        BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
        String l;
        while ((l = r.readLine()) != null)
        {
            if (l.equals("disable"))
            {
                long t0 = System.currentTimeMillis();
                m.invoke(ss, "disableAutoCompaction", new Object[]{ a[1], new String[]{ a[2] } }, new String[]{ "java.lang.String", "[Ljava.lang.String;" });
                System.out.println("disabled " + t0 + " " + System.currentTimeMillis()); System.out.flush();
            }
            else if (l.equals("enable"))
            {
                long t0 = System.currentTimeMillis();
                m.invoke(ss, "enableAutoCompaction", new Object[]{ a[1], new String[]{ a[2] } }, new String[]{ "java.lang.String", "[Ljava.lang.String;" });
                System.out.println("enabled " + t0 + " " + System.currentTimeMillis()); System.out.flush();
            }
            else if (l.equals("quit")) break;
        }
        c.close();
    }
}
