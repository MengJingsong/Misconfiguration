import java.io.*;
import java.util.*;

/**
 * U14 stage-2 HPROF scanner (design §2.5 `hprof_scan.py`, written in Java from the start as the design allows for a
 * 2 GB dump; same output). One sequential pass over an HPROF 1.0.2 file. Prints one JSON object:
 *  - per class: instance count and estimated shallow bytes (instance: align8(12 + primitive field bytes + 4 per reference
 *    field, whole hierarchy); object arrays align8(16 + 4 n); primitive arrays align8(16 + n * size)); compressed oops assumed;
 *  - top 40 classes by bytes, and the named classes of the design;
 *  - byte[] whose content contains 64 consecutive 'x' (the name marker): count and bytes (name-text share);
 *  - long[] of length 330 (reservoir buckets): count and bytes;
 *  - stack traces of threads whose frames mention a keyword (OutOfMemory, CreateTable, Schema, TableMetrics), first 25 frames.
 * usage: java -cp <dir> HprofScan <file.hprof>
 */
public class HprofScan
{
    static int idsz;
    static DataInputStream in;
    static long pos = 0;

    static int u1() throws IOException { pos += 1; return in.readUnsignedByte(); }
    static int u2() throws IOException { pos += 2; return in.readUnsignedShort(); }
    static int u4() throws IOException { pos += 4; return in.readInt(); }
    static long id() throws IOException { pos += idsz; return idsz == 8 ? in.readLong() : (in.readInt() & 0xffffffffL); }
    static void skip(long n) throws IOException
    {
        pos += n;
        while (n > 0)
        {
            long k = in.skip(n);
            if (k <= 0) { in.readByte(); k = 1; }
            n -= k;
        }
    }

    static int tsize(int t) { switch (t) { case 2: return idsz; case 4: case 8: return 1; case 5: case 9: return 2; case 6: case 10: return 4; case 7: case 11: return 8; } throw new RuntimeException("type " + t); }
    static long a8(long n) { return (n + 7) & ~7L; }

    static final String[] PRIM = {null, null, null, null, "boolean[]", "char[]", "float[]", "double[]", "byte[]", "short[]", "int[]", "long[]"};

    static class Cls { long superId; int prim; int refs; long nameId = -1; }

    static String esc(String s)
    {
        StringBuilder b = new StringBuilder();
        for (char c : s.toCharArray())
        {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.toString();
    }

    public static void main(String[] a) throws Exception
    {
        in = new DataInputStream(new BufferedInputStream(new FileInputStream(a[0]), 1 << 22));
        StringBuilder hdr = new StringBuilder();
        int ch;
        while ((ch = in.readUnsignedByte()) != 0) hdr.append((char) ch);
        pos = hdr.length() + 1;
        idsz = u4();
        in.readLong(); pos += 8;
        Map<Long, String> strings = new HashMap<>();
        Map<Long, Long> classNameId = new HashMap<>();      // class obj id -> name string id
        Map<Integer, Long> serialToClass = new HashMap<>();
        Map<Long, Cls> classes = new HashMap<>();
        Map<Long, long[]> instCount = new HashMap<>();      // class id -> {count}
        Map<Long, long[]> objArr = new HashMap<>();         // array class id -> {count, bytes}
        long[] primCount = new long[12], primBytes = new long[12];
        long markerN = 0, markerB = 0, l330N = 0, l330B = 0, objArrN = 0, objArrB = 0, segments = 0;
        Map<Long, long[]> frames = new HashMap<>();         // frame id -> {methodNameId, classSerial, line}
        List<long[]> traces = new ArrayList<>();            // {serial, threadSerial, frameIds...}
        byte[] buf = new byte[1 << 16];
        long fileLen = new File(a[0]).length();
        while (pos < fileLen)
        {
            int tag;
            try { tag = u1(); } catch (EOFException e) { break; }
            u4();
            long len = u4() & 0xffffffffL;
            long end = pos + len;
            if (tag == 0x01)
            {
                long sid = id();
                int n = (int) (len - idsz);
                byte[] b = new byte[n];
                in.readFully(b); pos += n;
                strings.put(sid, new String(b, "UTF-8"));
            }
            else if (tag == 0x02)
            {
                int serial = u4();
                long cid = id();
                u4();
                long nid = id();
                classNameId.put(cid, nid);
                serialToClass.put(serial, cid);
            }
            else if (tag == 0x04)
            {
                long fid = id();
                long mname = id();
                id(); id();
                int cser = u4();
                int line = u4();
                frames.put(fid, new long[]{mname, cser, line});
            }
            else if (tag == 0x05)
            {
                int ser = u4();
                int th = u4();
                int nf = u4();
                long[] t = new long[nf + 2];
                t[0] = ser; t[1] = th;
                for (int i = 0; i < nf; i++) t[i + 2] = id();
                traces.add(t);
            }
            else if (tag == 0x0C || tag == 0x1C)
            {
                segments++;
                while (pos < end)
                {
                    int st = u1();
                    switch (st)
                    {
                        case 0x21: {
                            id(); u4();
                            long cid = id();
                            long nb = u4() & 0xffffffffL;
                            skip(nb);
                            instCount.computeIfAbsent(cid, k -> new long[1])[0]++;
                            break;
                        }
                        case 0x22: {
                            id(); u4();
                            long n = u4() & 0xffffffffL;
                            long acid = id();
                            skip(n * idsz);
                            long[] v = objArr.computeIfAbsent(acid, k -> new long[2]);
                            v[0]++; v[1] += a8(16 + 4 * n);
                            objArrN++; objArrB += a8(16 + 4 * n);
                            break;
                        }
                        case 0x23: {
                            id(); u4();
                            long n = u4() & 0xffffffffL;
                            int t = u1();
                            long nb = n * tsize(t);
                            long sz = a8(16 + nb);
                            primCount[t]++; primBytes[t] += sz;
                            if (t == 8 && n >= 64)
                            {
                                // marker search: 64 consecutive 'x'
                                long left = nb; int run = 0; boolean hit = false;
                                while (left > 0)
                                {
                                    int k = (int) Math.min(buf.length, left);
                                    in.readFully(buf, 0, k); pos += k; left -= k;
                                    if (!hit)
                                        for (int i = 0; i < k; i++)
                                        {
                                            if (buf[i] == 'x') { if (++run >= 64) { hit = true; break; } }
                                            else run = 0;
                                        }
                                }
                                if (hit) { markerN++; markerB += sz; }
                            }
                            else
                            {
                                skip(nb);
                                if (t == 11 && n == 330) { l330N++; l330B += sz; }
                            }
                            break;
                        }
                        case 0x20: {
                            long cid = id(); u4();
                            Cls c = new Cls();
                            c.superId = id();
                            id(); id(); id(); id(); id();
                            u4();
                            int cp = u2();
                            for (int i = 0; i < cp; i++) { u2(); int t = u1(); skip(tsize(t)); }
                            int sc = u2();
                            for (int i = 0; i < sc; i++) { id(); int t = u1(); skip(tsize(t)); }
                            int fc = u2();
                            for (int i = 0; i < fc; i++)
                            {
                                id();
                                int t = u1();
                                if (t == 2) c.refs++; else c.prim += tsize(t);
                            }
                            classes.put(cid, c);
                            break;
                        }
                        case 0xFF: case 0x05: case 0x07: id(); break;
                        case 0x01: id(); id(); break;
                        case 0x02: case 0x03: case 0x08: id(); u4(); u4(); break;
                        case 0x04: case 0x06: id(); u4(); break;
                        default: throw new RuntimeException("unknown sub-record " + st + " at " + pos);
                    }
                }
            }
            else
            {
                skip(end - pos);
            }
        }
        // per-class tallies
        Map<String, long[]> perClass = new HashMap<>();   // name -> {count, bytes}
        long instN = 0, instB = 0;
        for (Map.Entry<Long, long[]> e : instCount.entrySet())
        {
            long cid = e.getKey();
            int prim = 0, refs = 0;
            Long c = cid;
            int guard = 0;
            while (c != null && c != 0 && classes.containsKey(c) && guard++ < 64)
            {
                Cls k = classes.get(c);
                prim += k.prim; refs += k.refs;
                c = k.superId;
            }
            long size = a8(12 + prim + 4L * refs);
            String nm = strings.getOrDefault(classNameId.getOrDefault(cid, -1L), "?" + cid).replace('/', '.');
            long[] v = perClass.computeIfAbsent(nm, k -> new long[2]);
            v[0] += e.getValue()[0]; v[1] += e.getValue()[0] * size;
            instN += e.getValue()[0]; instB += e.getValue()[0] * size;
        }
        for (Map.Entry<Long, long[]> e : objArr.entrySet())
        {
            String nm = strings.getOrDefault(classNameId.getOrDefault(e.getKey(), -1L), "?arr").replace('/', '.');
            long[] v = perClass.computeIfAbsent(nm, k -> new long[2]);
            v[0] += e.getValue()[0]; v[1] += e.getValue()[1];
        }
        long primN = 0, primB = 0;
        for (int t = 4; t < 12; t++)
        {
            if (primCount[t] == 0) continue;
            perClass.put(PRIM[t], new long[]{primCount[t], primBytes[t]});
            primN += primCount[t]; primB += primBytes[t];
        }
        List<Map.Entry<String, long[]>> all = new ArrayList<>(perClass.entrySet());
        all.sort((x, y) -> Long.compare(y.getValue()[1], x.getValue()[1]));
        StringBuilder o = new StringBuilder("{");
        o.append("\"header\":\"").append(esc(hdr.toString())).append("\",\"id_size\":").append(idsz);
        o.append(",\"file_bytes\":").append(fileLen).append(",\"segments\":").append(segments);
        o.append(",\"instances\":").append(instN).append(",\"instance_bytes\":").append(instB);
        o.append(",\"obj_arrays\":").append(objArrN).append(",\"obj_array_bytes\":").append(objArrB);
        o.append(",\"prim_arrays\":").append(primN).append(",\"prim_array_bytes\":").append(primB);
        o.append(",\"total_shallow_bytes\":").append(instB + objArrB + primB);
        o.append(",\"marker_byte_arrays\":").append(markerN).append(",\"marker_byte_array_bytes\":").append(markerB);
        o.append(",\"long330_arrays\":").append(l330N).append(",\"long330_bytes\":").append(l330B);
        o.append(",\"top40\":[");
        for (int i = 0; i < Math.min(40, all.size()); i++)
        {
            if (i > 0) o.append(',');
            o.append("[\"").append(esc(all.get(i).getKey())).append("\",").append(all.get(i).getValue()[0]).append(',').append(all.get(i).getValue()[1]).append(']');
        }
        o.append("],\"named\":{");
        String[] named = {"org.apache.cassandra.metrics.TableMetrics", "org.apache.cassandra.db.ColumnFamilyStore",
                          "org.apache.cassandra.metrics.CassandraMetricsRegistry$MetricName", "javax.management.ObjectName",
                          "org.apache.cassandra.metrics.DecayingEstimatedHistogramReservoir", "java.util.concurrent.atomic.AtomicLongArray",
                          "org.apache.cassandra.schema.TableMetadata", "org.apache.cassandra.schema.ColumnMetadata",
                          "java.lang.String", "byte[]", "long[]", "java.util.concurrent.ConcurrentHashMap$Node",
                          "com.sun.jmx.mbeanserver.NamedObject", "javax.management.ObjectName$Property"};
        for (int i = 0; i < named.length; i++)
        {
            long[] v = perClass.getOrDefault(named[i], new long[2]);
            if (i > 0) o.append(',');
            o.append('"').append(esc(named[i])).append("\":[").append(v[0]).append(',').append(v[1]).append(']');
        }
        o.append("},\"traces_total\":").append(traces.size()).append(",\"traces\":[");
        String[] keys = {"OutOfMemory", "CreateTable", "Schema", "TableMetrics", "MetricsRegistry"};
        int nt = 0;
        for (long[] t : traces)
        {
            List<String> fs = new ArrayList<>();
            boolean hit = false;
            for (int i = 2; i < t.length; i++)
            {
                long[] f = frames.get(t[i]);
                if (f == null) { fs.add("?"); continue; }
                Long cid = serialToClass.get((int) f[1]);
                String cn = cid == null ? "?" : strings.getOrDefault(classNameId.getOrDefault(cid, -1L), "?");
                cn = cn.substring(cn.lastIndexOf('/') + 1);
                String s = cn + "." + strings.getOrDefault(f[0], "?") + ":" + f[2];
                for (String k : keys) if (s.contains(k)) hit = true;
                fs.add(s);
            }
            if (!hit || nt >= 6) continue;
            if (nt++ > 0) o.append(',');
            o.append("{\"thread_serial\":").append(t[1]).append(",\"frames\":[");
            for (int i = 0; i < Math.min(25, fs.size()); i++)
            {
                if (i > 0) o.append(',');
                o.append('"').append(esc(fs.get(i))).append('"');
            }
            o.append("]}");
        }
        o.append("]}");
        System.out.println(o);
    }
}
