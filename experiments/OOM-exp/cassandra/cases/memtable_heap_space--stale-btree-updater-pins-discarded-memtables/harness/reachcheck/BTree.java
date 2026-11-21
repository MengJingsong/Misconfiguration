package org.apache.cassandra.utils.btree;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * R21 Step A (4) reach known-answer check (design §2.5); a test class, compiled into its own classpath, never the node's.
 * Holds 10 x byte[1048576] reachable only through one BTree$Updater.updateF, 5 reachable through it and through a static list,
 * 7 reachable only through the static list. hprof_reach.py must report reachable regions 22 and regions only via updateF 10.
 * usage: java -cp <dir> org.apache.cassandra.utils.btree.BTree <readyfile> <stopfile>
 */
public class BTree
{
    public static class Updater
    {
        Object updateF;
        Object comparator;
    }

    static Updater HELD;
    static final List<Object> LIST = new ArrayList<>();

    // built in its own method so that no local variable of main() (a frame GC root) references the arrays
    static void build()
    {
        Object[] viaF = new Object[15];
        for (int i = 0; i < 10; i++)
            viaF[i] = new byte[1048576];
        for (int i = 0; i < 5; i++)
        {
            byte[] b = new byte[1048576];
            viaF[10 + i] = b;
            LIST.add(b);
        }
        for (int i = 0; i < 7; i++)
            LIST.add(new byte[1048576]);
        HELD = new Updater();
        HELD.updateF = viaF;
    }

    public static void main(String[] a) throws Exception
    {
        build();
        new File(a[0]).createNewFile();
        File stop = new File(a[1]);
        while (!stop.exists())
            Thread.sleep(100);
        System.out.println(HELD.updateF != null && LIST.size() == 12);
    }
}
