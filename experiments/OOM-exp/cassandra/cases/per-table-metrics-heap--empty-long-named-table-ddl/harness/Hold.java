import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** U14 known-answer check (design §2.5): holds 1,000 distinct 222-character Strings containing the marker (64+ 'x')
 * and 500 long[330]; writes <ready>, exits when <stop> exists. */
public class Hold
{
    public static void main(String[] a) throws Exception
    {
        List<Object> keep = new ArrayList<>();
        StringBuilder x = new StringBuilder();
        for (int i = 0; i < 216; i++) x.append('x');
        for (int i = 0; i < 1000; i++)
            keep.add(new String(String.format("t%05d", i) + x));
        for (int i = 0; i < 500; i++)
            keep.add(new long[330]);
        new File(a[0]).createNewFile();
        File stop = new File(a[1]);
        while (!stop.exists())
            Thread.sleep(200);
        System.out.println(keep.size());
    }
}
