import org.junit.runner.JUnitCore;
import org.junit.runner.Request;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;

/** java RunOne <class> <method>: runs one JUnit method (used for the positive control testOver1GSize, B2e step 7). */
public class RunOne
{
    public static void main(String[] a) throws Exception
    {
        Result r = new JUnitCore().run(Request.method(Class.forName(a[0]), a[1]));
        System.out.println("RUNONE run=" + r.getRunCount() + " failures=" + r.getFailureCount() + " ignored=" + r.getIgnoreCount() + " timeMs=" + r.getRunTime());
        for (Failure f : r.getFailures())
            System.out.println("RUNONE FAILURE " + f.getTestHeader() + " " + f.getMessage());
        System.exit(r.wasSuccessful() ? 0 : 1);
    }
}
