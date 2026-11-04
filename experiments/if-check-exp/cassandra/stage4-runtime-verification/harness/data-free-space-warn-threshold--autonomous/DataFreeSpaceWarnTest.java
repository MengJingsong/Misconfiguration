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
 * Stage-4 harness (set A batch 8) for data-free-space-warn-threshold--autonomous, unit tier.
 * One JVM per case. System properties:
 *   stage4.dirs   comma-separated data_file_directories (absolute, already created, on the volumes under test)
 *   stage4.label  case label printed in every STAGE4 line
 *   stage4.control  "true" to also run the Directories.getWriteableLocation positive control
 * cassandra.config (file:///...) is given by the run script.
 * Prints STAGE4 lines; the run script compares them with EXPECTED lines.
 */
public class DataFreeSpaceWarnTest
{
    @Test
    public void run() throws Exception
    {
        String label = System.getProperty("stage4.label", "?");
        String[] dirs = System.getProperty("stage4.dirs").split(",");
        boolean control = Boolean.getBoolean("stage4.control");

        Logger l = (Logger) LoggerFactory.getLogger(DatabaseDescriptor.class);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        l.addAppender(app);
        l.setLevel(Level.DEBUG);

        // independent expected value: FileStore.getUnallocatedSpace of each configured directory
        long sum = 0;
        StringBuilder per = new StringBuilder();
        for (String d : dirs)
        {
            FileStore fs = Files.getFileStore(new File(d).toPath());
            long u = fs.getUnallocatedSpace();
            per.append(d).append('=').append(u).append(';');
            sum += u;
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

        List<String> warns = new ArrayList<>();
        for (ILoggingEvent e : app.list)
            if (e.getLevel() == Level.WARN && e.getFormattedMessage().contains("free across all data volumes"))
                warns.add(e.getFormattedMessage());

        System.out.println("STAGE4 [" + label + "] dirs=" + String.join(",", dirs));
        System.out.println("STAGE4 [" + label + "] unallocated_per_dir=" + per + " sum_bytes=" + sum + " threshold_bytes=" + (64L << 30) + " sum_lt_threshold=" + (sum < (64L << 30)));
        System.out.println("STAGE4 [" + label + "] warn_count=" + warns.size());
        for (String w : warns)
            System.out.println("STAGE4 [" + label + "] warn_text=" + w);
        System.out.println("STAGE4 [" + label + "] init_returned=" + returned + " error=" + err);

        if (returned)
        {
            // Config snapshot: every public non-static field except data_file_directories, as a sorted dump
            TreeMap<String, String> snap = new TreeMap<>();
            Config c = DatabaseDescriptor.getRawConfig();
            for (Field f : Config.class.getFields())
            {
                if (Modifier.isStatic(f.getModifiers()) || f.getName().equals("data_file_directories"))
                    continue;
                Object v = f.get(c);
                snap.put(f.getName(), (v == null ? "null" : (v.getClass().isArray() ? java.util.Arrays.deepToString(new Object[]{ v }) : v.toString())).replaceAll("@[0-9a-f]+", "@x"));
            }
            int h = snap.toString().hashCode();
            System.out.println("STAGE4 [" + label + "] config_fields=" + snap.size() + " config_hash=" + h);
            if (System.getProperty("stage4.dumpconfig") != null)
                Files.write(new File(System.getProperty("stage4.dumpconfig")).toPath(), (snap.toString().replace(", ", "\n")).getBytes());
        }

        if (control && returned)
        {
            TableMetadata md = TableMetadata.builder("stage4ks", "t").addPartitionKeyColumn("k", Int32Type.instance).build();
            Directories.DataDirectory[] dd = new Directories.DataDirectory[dirs.length];
            for (int i = 0; i < dirs.length; i++)
                dd[i] = new Directories.DataDirectory(new File(dirs[i]).toPath());
            Directories ds = new Directories(md, dd);
            long avail = 0;
            for (Directories.DataDirectory x : dd)
                avail = Math.max(avail, x.getAvailableSpace());
            System.out.println("STAGE4 [" + label + "] control max_dir_available=" + avail);
            long[] reqs = { avail / 2, avail * 2 };
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
                System.out.println("STAGE4 [" + label + "] control request=" + r + " result=" + res);
            }
        }
    }
}
