package org.apache.cassandra.cache;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.Iterator;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.Test;
import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.io.sstable.AbstractRowIndexEntry;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.service.CacheService;

/**
 * Stage-4 harness for cache-keys-to-save-writer-keysToSave--autonomous (unit tier, B2).
 * Measurements are written as "key=value" lines to $STAGE4_OUT/unit.txt (and echoed as "STAGE4 key=value");
 * the verdict is made by analyze_unit.py, not here. Env STAGE4_N overrides N (shakedown / instrument check only).
 */
public class KeysToSaveWriterTest extends CQLTester
{
    static PrintWriter out;
    static final Pattern SAVED = Pattern.compile("Saved (\\w+) \\((\\d+) items\\)");
    static final int[] KS = { 1, 100, 500, 1000, 0, Integer.MAX_VALUE, 2000 };
    static final int[] CKS = { 100, 0 };

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    @Test
    public void all() throws Exception
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        int n = Integer.parseInt(System.getenv().getOrDefault("STAGE4_N", "1000"));
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        Logger lg = (Logger) LoggerFactory.getLogger(AutoSavingCache.class);
        lg.setLevel(Level.INFO);
        ListAppender<ILoggingEvent> app = new ListAppender<>();
        app.start();
        lg.addAppender(app);
        try
        {
            rec("N=" + n);
            rec("keyCacheCapacity=" + CacheService.instance.keyCache.getCapacity());
            rec("counterCacheCapacity=" + CacheService.instance.counterCache.getCapacity());
            keyArms(n, app);
            counterArms(n, app);
            rec("done=1");
        }
        finally
        {
            lg.detachAppender(app);
            out.close();
        }
    }

    static long len(File f) { return f.exists() ? f.length() : -1; }

    static void cleanSaved(AutoSavingCache<?, ?> c)
    {
        File d = c.getCacheDataPath("g").parent();
        File[] fs = d.tryList();
        if (fs != null)
            for (File f : fs)
                if (f.name().startsWith(c.getCacheDataPath("g").name().split("-")[0]))
                    f.tryDelete();
    }

    static int logged(ListAppender<ILoggingEvent> app, String type)
    {
        int r = -1;
        for (ILoggingEvent e : app.list)
        {
            Matcher m = SAVED.matcher(e.getFormattedMessage());
            if (m.find() && m.group(1).equals(type))
                r = Integer.parseInt(m.group(2));
        }
        return r;
    }

    void keyArms(int n, ListAppender<ILoggingEvent> app) throws Exception
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)");
        for (int i = 0; i < n; i++)
            execute("INSERT INTO %s (k, v) VALUES (?, ?)", i, i);
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        flush();
        SSTableReader sst = cfs.getLiveSSTables().iterator().next();
        AutoSavingCache<KeyCacheKey, AbstractRowIndexEntry> kc = CacheService.instance.keyCache;
        boolean first = true;
        for (int k : KS)
        {
            kc.clear();
            cleanSaved(kc);
            for (int i = 0; i < n; i++)
                sst.getPosition(cfs.decorateKey(Int32Type.instance.decompose(i)), SSTableReader.Operator.EQ);
            for (int rep = 0; rep < 5; rep++)
                for (int i = 0; i < Math.min(100, n); i++)
                    sst.getPosition(cfs.decorateKey(Int32Type.instance.decompose(i)), SSTableReader.Operator.EQ);
            int startSize = kc.size();
            long startW = kc.weightedSize();
            rec("key K=" + k + " start_size=" + startSize + " start_weighted=" + startW);
            if (first && startSize != n)
                throw new AssertionError("first-trigger check: key cache size " + startSize + " != N " + n);
            first = false;
            app.list.clear();
            kc.submitWrite(k).get();
            int nLog = logged(app, "KeyCache");
            long l = len(kc.getCacheDataPath("g"));
            long lc = len(kc.getCacheCrcPath("g"));
            long lm = len(kc.getCacheMetadataPath("g"));
            rec("key K=" + k + " n_logged=" + nLog + " file_len=" + l + " crc_len=" + lc + " meta_len=" + lm
                + " size_after=" + kc.size() + " weighted_after=" + kc.weightedSize());
            kc.clear();
            int loaded = kc.loadSaved();
            int hot = 0;
            Iterator<KeyCacheKey> it = kc.keyIterator();
            while (it.hasNext())
            {
                KeyCacheKey key = it.next();
                int v = Int32Type.instance.compose(ByteBuffer.wrap(key.key));
                if (v < 100)
                    hot++;
            }
            rec("key K=" + k + " reload_count=" + loaded + " size_reloaded=" + kc.size() + " hot_in_saved=" + hot);
        }
    }

    void counterArms(int n, ListAppender<ILoggingEvent> app) throws Exception
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, c counter)");
        AutoSavingCache<CounterCacheKey, org.apache.cassandra.db.ClockAndCount> cc = CacheService.instance.counterCache;
        for (int k : CKS)
        {
            cc.clear();
            cleanSaved(cc);
            for (int i = 0; i < n; i++)
                execute("UPDATE %s SET c = c + 1 WHERE k = ?", i);
            int startSize = cc.size();
            rec("ctr K=" + k + " start_size=" + startSize);
            app.list.clear();
            cc.submitWrite(k).get();
            long l = len(cc.getCacheDataPath("g"));
            rec("ctr K=" + k + " n_logged=" + logged(app, "CounterCache") + " file_len=" + l);
            cc.clear();
            int loaded = cc.loadSaved();
            rec("ctr K=" + k + " reload_count=" + loaded + " size_reloaded=" + cc.size());
        }
    }
}
