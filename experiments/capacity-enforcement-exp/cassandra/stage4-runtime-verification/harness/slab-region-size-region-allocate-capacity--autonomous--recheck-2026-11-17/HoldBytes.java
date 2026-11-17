import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** Known-answer instrument check: waits for <go file>, then allocates <k> live byte[1048576] (the size of one slab region),
 *  writes <done file>, and holds them until <stop file> exists. The histogram [B delta must be k x 1,048,592 B. */
public class HoldBytes
{
    public static void main(String[] a) throws Exception
    {
        int k = Integer.parseInt(a[0]);
        File go = new File(a[1]), done = new File(a[2]), stop = new File(a[3]);
        while (!go.exists()) Thread.sleep(100);
        List<byte[]> keep = new ArrayList<>();
        for (int i = 0; i < k; i++) keep.add(new byte[1048576]);
        done.createNewFile();
        while (!stop.exists()) Thread.sleep(100);
        System.out.println("held " + keep.size());
    }
}
