package org.apache.cassandra.service;

import java.lang.reflect.Field;
import java.util.Arrays;
import com.google.common.cache.Cache;
import com.google.common.collect.ImmutableList;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.utils.ObjectSizes;

public class ParentRepairStatusCapTest
{
    @BeforeClass
    public static void setup() { SchemaLoader.prepareServer(); }

    @Test
    public void sweep() throws Exception
    {
        int m = Integer.getInteger("o127.m", 50000);
        int len = Integer.getInteger("o127.len", 1000);
        int every = Integer.getInteger("o127.every", 5000);
        ActiveRepairService ars = ActiveRepairService.instance();   // first touch: reads the -D now
        Field f = ActiveRepairService.class.getDeclaredField("repairStatusByCmd");
        f.setAccessible(true);
        Cache<Integer, ?> cache = (Cache<Integer, ?>) f.get(ars);
        char[] pad = new char[len]; Arrays.fill(pad, 'x');
        String base = new String(pad);
        System.out.println("O127 cap=" + System.getProperty("cassandra.parent_repair_status_cache_size", "default")
                           + " m=" + m + " len=" + len + " i=0 size=" + cache.size() + " deep=" + ObjectSizes.measureDeep(cache));
        for (int i = 1; i <= m; i++)
        {
            String msg = i + base;                                  // distinct String per entry
            ars.recordRepairStatus(i, ActiveRepairService.ParentRepairStatus.COMPLETED, ImmutableList.of(msg));
            if (i % every == 0)
            {
                cache.cleanUp();
                System.out.println("O127 i=" + i + " size=" + cache.size() + " deep=" + ObjectSizes.measureDeep(cache));
            }
        }
        cache.cleanUp();
        int present = 0, presentLastN = 0;
        long cap = Long.getLong("cassandra.parent_repair_status_cache_size", 100000L);
        for (int i = 1; i <= m; i++)
            if (ars.getRepairStatus(i) != null) { present++; if (i > m - cap) presentLastN++; }
        System.out.println("O127 FINAL size=" + cache.size() + " present=" + present + " presentInLastN=" + presentLastN
                           + " deep=" + ObjectSizes.measureDeep(cache));
    }
}
