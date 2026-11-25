import java.nio.file.Paths;
import jdk.jfr.consumer.*;

public class JfrDob
{
    public static void main(String[] a) throws Exception
    {
        for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0])))
        {
            if (!e.getEventType().getName().equals("jdk.ObjectAllocationOutsideTLAB") || e.getStackTrace() == null)
                continue;
            boolean dob = false, local = false;
            for (RecordedFrame f : e.getStackTrace().getFrames())
            {
                String m = f.getMethod().getType().getName() + "." + f.getMethod().getName();
                if (m.equals("org.apache.cassandra.io.util.DataOutputBuffer.expandToFit")) dob = true;
                if (m.equals("org.apache.cassandra.db.ReadResponse$LocalDataResponse.build")) local = true;
            }
            if (dob && local)
                System.out.println(e.getStartTime() + " " + e.getThread("eventThread").getJavaName()
                                   + " " + e.getClass("objectClass").getName() + " " + e.getLong("allocationSize"));
        }
    }
}
