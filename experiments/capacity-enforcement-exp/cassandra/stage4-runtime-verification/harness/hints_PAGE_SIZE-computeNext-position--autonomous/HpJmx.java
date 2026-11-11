/*
 * Stage-4 harness, cluster tier (B3d, as amended 2026-10-26) of hints_PAGE_SIZE-computeNext-position--autonomous.
 * One JMX read of node 1's hint counters (local JMX on 127.0.0.1:<port>, no auth); replaces `nodetool sjk mx`, which exits 0 on failure.
 *   java HpJmx once <port>
 *     -> RESULT total_hints=<Storage.TotalHints Count> succeeded=<HintsService.HintsSucceeded Count>
 *               failed=<HintsService.HintsFailed Count> timed_out=<HintsService.HintsTimedOut Count>
 *   TotalHints: StorageMetrics.totalHints, +1 per target host per hint written (HintsService.java:172).
 *   HintsSucceeded/Failed/TimedOut: marked once per page by HintsDispatcher.updateMetrics (HintsDispatcher.java:153, 167-172).
 * A bean not yet registered reads 0. On failure prints "RESULT ERR <exception>" and exits 1.
 */
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class HpJmx
{
    public static void main(String[] a)
    {
        try
        {
            JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[1] + "/jmxrmi");
            try (JMXConnector c = JMXConnectorFactory.connect(url))
            {
                MBeanServerConnection m = c.getMBeanServerConnection();
                System.out.println("RESULT total_hints=" + num(m, "org.apache.cassandra.metrics:type=Storage,name=TotalHints")
                                   + " succeeded=" + num(m, "org.apache.cassandra.metrics:type=HintsService,name=HintsSucceeded")
                                   + " failed=" + num(m, "org.apache.cassandra.metrics:type=HintsService,name=HintsFailed")
                                   + " timed_out=" + num(m, "org.apache.cassandra.metrics:type=HintsService,name=HintsTimedOut"));
            }
        }
        catch (Exception e)
        {
            System.out.println("RESULT ERR " + e);
            System.exit(1);
        }
    }

    // A HintsService meter is registered when HintsServiceMetrics is first loaded (first dispatch); before that the bean is absent: 0.
    static long num(MBeanServerConnection m, String bean) throws Exception
    {
        try
        {
            return ((Number) m.getAttribute(new ObjectName(bean), "Count")).longValue();
        }
        catch (javax.management.InstanceNotFoundException e)
        {
            return 0;
        }
    }
}
