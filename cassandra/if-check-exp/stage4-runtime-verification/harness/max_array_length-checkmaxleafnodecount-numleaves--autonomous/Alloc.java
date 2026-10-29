package stage4;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Byteman helper (case max_points_in_leaf_node / max_array_length cluster tier, 2026-10-28): thread-allocated bytes and a one-line description of the components
 *  returned by NumericIndexWriter.writeCompleteSegment. Compiled into the run copy's build/classes/main (a throwaway copy). */
public class Alloc
{
    public static long bytes()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    public static int maxPoints(Object numericIndexWriter)
    {
        try
        {
            Field f = numericIndexWriter.getClass().getDeclaredField("writer"); f.setAccessible(true);
            Object w = f.get(numericIndexWriter);
            Method m = w.getClass().getMethod("getMaxPointsInLeafNode");
            return (Integer) m.invoke(w);
        }
        catch (Throwable t) { return -1; }
    }

    public static String attrs(Object comps)
    {
        try
        {
            Class<?> ic = Class.forName("org.apache.cassandra.index.sai.disk.format.IndexComponent");
            Object tree = comps.getClass().getMethod("get", ic).invoke(comps, Enum.valueOf((Class) ic, "BALANCED_TREE"));
            Object post = comps.getClass().getMethod("get", ic).invoke(comps, Enum.valueOf((Class) ic, "POSTING_LISTS"));
            if (tree == null) return "empty";
            java.util.Map<?, ?> at = (java.util.Map<?, ?>) tree.getClass().getField("attributes").get(tree);
            long tl = tree.getClass().getField("length").getLong(tree), pl = post == null ? -1 : post.getClass().getField("length").getLong(post);
            return "num_leaves=" + at.get("num_leaves") + " num_values=" + at.get("num_values") + " max_points_in_leaf_node=" + at.get("max_points_in_leaf_node")
                   + " bytes_per_value=" + at.get("bytes_per_value") + " treeLen=" + tl + " postLen=" + pl;
        }
        catch (Throwable t) { return "attrs-error " + t; }
    }
}
