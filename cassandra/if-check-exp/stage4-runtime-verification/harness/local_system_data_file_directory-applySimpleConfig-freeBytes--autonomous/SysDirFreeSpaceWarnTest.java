package org.apache.cassandra.config;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.Test;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.io.FSWriteError;
import org.apache.cassandra.schema.TableMetadata;

/**
 * Stage-4 harness (set A batch 8, tag ls) for local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous, unit tier.
 * One JVM per case. System properties: stage4.label, stage4.sysdir (the configured local_system_data_file_directory, or empty when
 * the yaml leaves it unset; used only for the independent free-space read and the admission probe), stage4.dumpconfig (optional file).
 * cassandra.config (file:///...) is given by the run script. Prints STAGE4 lines.
 */
public class SysDirFreeSpaceWarnTest
{
    @Test
    public void run() throws Exception
    {
        String label = System.getProperty("stage4.label", "?");
        String sysdir = System.getProperty("stage4.sysdir", "");

        Logger l = (Logger) LoggerFactory.getLogger(DatabaseDescriptor.class);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        l.addAppender(app);
        l.setLevel(Level.DEBUG);

        long unalloc = -1;
        if (!sysdir.isEmpty())
        {
            FileStore fs = Files.getFileStore(new File(sysdir).toPath());
            unalloc = fs.getUnallocatedSpace();
        }

        boolean returned = false;
        String err = "none";
        try
        {
            DatabaseDescriptor.daemonInitialization();
            returned = true;
        }
        catch (Throwable t)
        {
            err = t.getClass().getName() + ": " + t.getMessage();
        }

        List<String> sys = new ArrayList<>();
        int dataWarn = 0;
        for (ILoggingEvent e : app.list)
        {
            if (e.getLevel() != Level.WARN) continue;
            String m = e.getFormattedMessage();
            if (m.contains("free in the system data volume")) sys.add(m);
            if (m.contains("free across all data volumes")) dataWarn++;
        }
        long ONE_GIB = 1L << 30;
        System.out.println("STAGE4 [" + label + "] sysdir=" + (sysdir.isEmpty() ? "(unset)" : sysdir));
        System.out.println("STAGE4 [" + label + "] unallocated_bytes=" + unalloc + " one_gib=" + ONE_GIB + " lt_one_gib=" + (unalloc >= 0 && unalloc < ONE_GIB));
        System.out.println("STAGE4 [" + label + "] sys_warn_count=" + sys.size() + " data_warn_count=" + dataWarn);
        for (String w : sys)
            System.out.println("STAGE4 [" + label + "] sys_warn_text=" + w);
        System.out.println("STAGE4 [" + label + "] init_returned=" + returned + " error=" + err);

        if (returned)
        {
            System.out.println("STAGE4 [" + label + "] raw_local_system_data_file_directory=" + DatabaseDescriptor.getRawConfig().local_system_data_file_directory
                               + " useSpecificLocation=" + DatabaseDescriptor.useSpecificLocationForLocalSystemData());
            TreeMap<String, String> snap = new TreeMap<>();
            Config c = DatabaseDescriptor.getRawConfig();
            for (Field f : Config.class.getFields())
            {
                if (Modifier.isStatic(f.getModifiers()) || f.getName().equals("data_file_directories") || f.getName().equals("local_system_data_file_directory"))
                    continue;
                Object v = f.get(c);
                snap.put(f.getName(), (v == null ? "null" : (v.getClass().isArray() ? java.util.Arrays.deepToString(new Object[]{ v }) : v.toString())).replaceAll("@[0-9a-f]+", "@x"));
            }
            System.out.println("STAGE4 [" + label + "] config_fields=" + snap.size() + " config_hash=" + snap.toString().hashCode());
            if (System.getProperty("stage4.dumpconfig") != null)
                Files.write(new File(System.getProperty("stage4.dumpconfig")).toPath(), (snap.toString().replace(", ", "\n")).getBytes());
        }

        if (returned && !sysdir.isEmpty())
        {
            // runtime admission on the sysdata directory (Directories.getWriteableLocation, the check that does bind)
            TableMetadata md = TableMetadata.builder("stage4ks", "t").addPartitionKeyColumn("k", Int32Type.instance).build();
            Directories.DataDirectory dd = new Directories.DataDirectory(new File(sysdir).toPath());
            Directories ds = new Directories(md, new Directories.DataDirectory[]{ dd });
            long avail = dd.getAvailableSpace();
            System.out.println("STAGE4 [" + label + "] probe available_bytes=" + avail + " min_free_space_per_drive=" + DatabaseDescriptor.getMinFreeSpacePerDriveInBytes());
            long[] reqs = { 300L << 20, avail * 2 };
            for (long r : reqs)
            {
                String res;
                try
                {
                    ds.getWriteableLocation(r);
                    res = "returned_directory";
                }
                catch (FSWriteError e)
                {
                    res = "threw_" + e.getClass().getSimpleName();
                }
                System.out.println("STAGE4 [" + label + "] probe request=" + r + " result=" + res);
            }
        }
    }
}
