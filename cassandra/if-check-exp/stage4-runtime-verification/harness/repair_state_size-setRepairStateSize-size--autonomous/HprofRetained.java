// HprofRetained — retained heap of one cache inside one heap dump (cluster re-run of
// repair_state_size-setRepairStateSize-size--autonomous, Amendment 2026-10-28 B3d (6)). Observe-only: it reads an HPROF file
// written by `jcmd <pid> GC.heap_dump` and the class histogram taken just before it (for the JVM's own shallow instance sizes).
//
// usage: java HprofRetained.java <dump.hprof> <histogram.txt> <cutClass> <cutField> <valueClass>
//   A = bytes reachable from the GC roots (every root sub-record, and every class);
//   B = the same with the one reference held in field <cutField> of every <cutClass> instance removed;
//   C = the same as A, but no object of class <valueClass> is entered;
//   R_cache = A - B (everything only the field's referent keeps alive), R_values = A - C (the values and what only they keep).
// Instance sizes come from the histogram (bytes / instances of the class's row); arrays are 16 B + length x element size,
// rounded up to 8 (compressed oops and class pointers: 1 GiB heap); java.lang.Class objects are roots and are not sized.
import java.io.*;
import java.nio.*;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.*;

public class HprofRetained {
    static ByteBuffer b; static int idSize;
    static long id() { return idSize == 8 ? b.getLong() : (b.getInt() & 0xffffffffL); }
    static int vsize(int t) { switch (t) { case 2: return idSize; case 4: case 8: return 1; case 5: case 9: return 2; case 6: case 10: return 4; case 7: case 11: return 8; default: throw new IllegalStateException("type " + t); } }
    static int esize(int t) { switch (t) { case 4: case 8: return 1; case 5: case 9: return 2; case 6: case 10: return 4; case 7: case 11: return 8; default: throw new IllegalStateException("etype " + t); } }
    static long align8(long x) { return (x + 7) & ~7L; }

    static final class Cls { long id, sup, loader; String name; int[] ftypes; String[] fnames; long[] statics; }
    static Map<Long, String> utf8 = new HashMap<>(); static Map<Long, Long> classNameId = new HashMap<>();
    static Map<Long, Cls> classes = new HashMap<>();
    // objects
    static long[] oid = new long[1 << 20]; static int[] okind = new int[1 << 20]; static long[] oaux = new long[1 << 20]; static int[] opos = new int[1 << 20]; static int no = 0;
    // kind 0 instance (aux = class id, pos = data start), 1 obj array (aux = array class id, pos = data start, len in olen), 2 prim array, 3 class
    static int[] olen = new int[1 << 20];
    static List<Long> roots = new ArrayList<>();

    static void add(long id, int kind, long aux, int pos, int len) {
        if (no == oid.length) { int n = no * 2; oid = Arrays.copyOf(oid, n); okind = Arrays.copyOf(okind, n); oaux = Arrays.copyOf(oaux, n); opos = Arrays.copyOf(opos, n); olen = Arrays.copyOf(olen, n); }
        oid[no] = id; okind[no] = kind; oaux[no] = aux; opos[no] = pos; olen[no] = len; no++;
    }

    public static void main(String[] a) throws Exception {
        String dump = a[0], hist = a[1], cutClass = a[2], cutField = a[3], valueClass = a[4];
        Map<String, Long> histSize = new HashMap<>(); long histTotal = -1, histClassBytes = 0;
        for (String l : Files.readAllLines(Paths.get(hist))) {
            String[] p = l.trim().split("\\s+");
            if (p.length >= 3 && p[0].equals("Total")) histTotal = Long.parseLong(p[2]);
            else if (p.length >= 4 && p[0].endsWith(":")) {
                long inst = Long.parseLong(p[1]), bytes = Long.parseLong(p[2]);
                if (p[3].equals("java.lang.Class")) histClassBytes = bytes;
                if (!p[3].startsWith("[") && inst > 0) histSize.putIfAbsent(p[3], bytes / inst);
            }
        }
        try (FileChannel ch = FileChannel.open(Paths.get(dump))) {
            b = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size()); b.order(ByteOrder.BIG_ENDIAN);
        }
        while (b.get() != 0) { }
        idSize = b.getInt(); b.getLong();
        while (b.hasRemaining()) {
            int tag = b.get() & 0xff; b.getInt(); long len = b.getInt() & 0xffffffffL; int end = (int) (b.position() + len);
            if (tag == 0x01) { long i = id(); byte[] s = new byte[(int) (len - idSize)]; b.get(s); utf8.put(i, new String(s, "UTF-8")); }
            else if (tag == 0x02) { b.getInt(); long cid = id(); b.getInt(); long nid = id(); classNameId.put(cid, nid); }
            else if (tag == 0x0C || tag == 0x1C) { heap(end); }
            b.position(end);
        }
        for (Cls c : classes.values()) {
            Long nid = classNameId.get(c.id); c.name = nid == null ? ("?" + c.id) : utf8.get(nid).replace('/', '.');
            for (int j = 0; j < c.fnames.length; j++) c.fnames[j] = utf8.get(Long.parseLong(c.fnames[j]));
        }
        // index
        Integer[] ord = new Integer[no]; for (int i = 0; i < no; i++) ord[i] = i;
        final long[] ids = oid; Arrays.sort(ord, (x, y) -> Long.compare(ids[x], ids[y]));
        long[] sid = new long[no]; int[] sidx = new int[no]; for (int i = 0; i < no; i++) { sid[i] = oid[ord[i]]; sidx[i] = ord[i]; }
        // per-class instance field layouts including superclasses (this class first, then super, as HPROF writes them)
        Map<Long, int[]> ltypes = new HashMap<>(); Map<Long, String[]> lnames = new HashMap<>();
        for (Cls c : classes.values()) {
            List<Integer> t = new ArrayList<>(); List<String> n = new ArrayList<>();
            for (Cls k = c; k != null; k = classes.get(k.sup)) { for (int j = 0; j < k.ftypes.length; j++) { t.add(k.ftypes[j]); n.add(k.fnames[j]); } }
            ltypes.put(c.id, t.stream().mapToInt(Integer::intValue).toArray()); lnames.put(c.id, n.toArray(new String[0]));
        }
        // sizes and edges
        long[] size = new long[no]; int[] rs = new int[no + 1]; int[] rt = new int[Math.max(16, no * 3)]; int ne = 0;
        int cutSrc = -1; List<int[]> cutEdges = new ArrayList<>();
        boolean[] isValue = new boolean[no]; int fallbackObjs = 0; long fallbackBytes = 0; Set<String> fallbackNames = new TreeSet<>();
        int[] isClass = new int[no];
        for (int i = 0; i < no; i++) {
            rs[i] = ne;
            int k = okind[i];
            if (k == 0) {
                Cls c = classes.get(oaux[i]); String nm = c == null ? "?" : c.name;
                Long hs = histSize.get(nm);
                int[] ft = ltypes.get(oaux[i]); String[] fn = lnames.get(oaux[i]);
                if (hs != null) size[i] = hs; else {
                    long s = 12; for (int t : ft) s += (t == 2 ? 4 : esize(t)); size[i] = align8(s); fallbackObjs++; fallbackBytes += size[i]; fallbackNames.add(nm);
                }
                if (nm.equals(valueClass)) isValue[i] = true;
                b.position(opos[i]);
                boolean cut = nm.equals(cutClass);
                for (int j = 0; j < ft.length; j++) {
                    if (ft[j] == 2) { long r = id(); int ti = find(sid, sidx, r); if (ti >= 0) {
                        if (ne == rt.length) rt = Arrays.copyOf(rt, rt.length * 2);
                        rt[ne++] = ti; if (cut && fn[j].equals(cutField)) cutEdges.add(new int[]{i, ti}); } }
                    else b.position(b.position() + vsize(ft[j]));
                }
            } else if (k == 1) {
                size[i] = align8(16 + 4L * olen[i]);
                b.position(opos[i]);
                for (int j = 0; j < olen[i]; j++) { long r = id(); int ti = find(sid, sidx, r); if (ti >= 0) { if (ne == rt.length) rt = Arrays.copyOf(rt, rt.length * 2); rt[ne++] = ti; } }
            } else if (k == 2) {
                size[i] = align8(16 + (long) esize((int) oaux[i]) * olen[i]);
            } else {
                isClass[i] = 1; size[i] = 0;
                Cls c = classes.get(oid[i]);
                long[] refs = new long[c.statics.length + 2]; System.arraycopy(c.statics, 0, refs, 0, c.statics.length); refs[c.statics.length] = c.sup; refs[c.statics.length + 1] = c.loader;
                for (long r : refs) { int ti = find(sid, sidx, r); if (ti >= 0) { if (ne == rt.length) rt = Arrays.copyOf(rt, rt.length * 2); rt[ne++] = ti; } }
            }
        }
        rs[no] = ne;
        List<Integer> rootIdx = new ArrayList<>();
        for (long r : roots) { int ti = find(sid, sidx, r); if (ti >= 0) rootIdx.add(ti); }
        for (int i = 0; i < no; i++) if (isClass[i] == 1) rootIdx.add(i);
        BitSet A = reach(no, rs, rt, rootIdx, null, null);
        Set<Long> cutSet = new HashSet<>(); for (int[] e : cutEdges) cutSet.add(((long) e[0] << 32) | e[1]);
        BitSet B = reach(no, rs, rt, rootIdx, cutSet, null);
        BitSet C = reach(no, rs, rt, rootIdx, null, isValue);
        long bytesA = sum(A, size), bytesB = sum(B, size), bytesC = sum(C, size);
        int valA = 0, valB = 0, valAll = 0; for (int i = 0; i < no; i++) if (isValue[i]) { valAll++; if (A.get(i)) valA++; if (B.get(i)) valB++; }
        int cutTargetsReachableInB = 0; for (int[] e : cutEdges) if (B.get(e[1])) cutTargetsReachableInB++;
        int fbInR = 0; for (int i = 0; i < no; i++) if (A.get(i) && !B.get(i) && okind[i] == 0 && !histSize.containsKey(classes.get(oaux[i]) == null ? "?" : classes.get(oaux[i]).name)) fbInR++;
        System.out.println("HPROF file=" + dump + " idSize=" + idSize + " objects=" + no + " classes=" + classes.size() + " roots=" + roots.size() + " edges=" + ne);
        System.out.println("HIST total=" + histTotal + " classBytes=" + histClassBytes + " totalMinusClass=" + (histTotal - histClassBytes));
        System.out.println("REACH A=" + bytesA + " B=" + bytesB + " C=" + bytesC + " objsA=" + A.cardinality());
        System.out.println("CUT class=" + cutClass + " field=" + cutField + " edges=" + cutEdges.size() + " targetsReachableAfterCut=" + cutTargetsReachableInB);
        System.out.println("VALUE class=" + valueClass + " inDump=" + valAll + " reachable=" + valA + " reachableAfterCut=" + valB);
        System.out.println("RETAINED R_cache=" + (bytesA - bytesB) + " R_values=" + (bytesA - bytesC) + " structure=" + ((bytesA - bytesB) - (bytesA - bytesC)));
        System.out.println("FALLBACK sizedByLayout objs=" + fallbackObjs + " bytes=" + fallbackBytes + " inR_cache=" + fbInR + " classes=" + (fallbackNames.size() > 12 ? fallbackNames.size() + " names" : fallbackNames.toString()));
        BitSet all = new BitSet(no); all.set(0, no); BitSet un = (BitSet) all.clone(); un.andNot(A);
        System.out.println("UNREACHED objs=" + un.cardinality() + " bytes=" + sum(un, size) + " (in the dump, not reached from the roots)");
        breakdown("R_values", A, C, size, isClass);
        BitSet structOnly = (BitSet) A.clone(); structOnly.andNot(B); BitSet inValues = (BitSet) A.clone(); inValues.andNot(C); structOnly.andNot(inValues);
        BitSet compl = (BitSet) A.clone(); compl.andNot(structOnly); breakdown("structure", A, compl, size, isClass);
        if (System.getenv("HPR_UNREACHED") != null) breakdown("unreached", all, A, size, isClass);
    }

    static void breakdown(String label, BitSet A, BitSet X, long[] size, int[] isClass) {
        TreeMap<String, long[]> m = new TreeMap<>();
        for (int i = A.nextSetBit(0); i >= 0; i = A.nextSetBit(i + 1)) if (!X.get(i)) {
            String nm; int k = okind[i];
            if (k == 0) { Cls c = classes.get(oaux[i]); nm = c == null ? "?" : c.name; }
            else if (k == 1) { Cls c = classes.get(oaux[i]); nm = (c == null ? "[?" : c.name) + " len=" + olen[i]; }
            else if (k == 2) nm = "prim" + oaux[i] + "[] len=" + olen[i];
            else nm = "class";
            long[] v = m.computeIfAbsent(nm, z -> new long[2]); v[0]++; v[1] += size[i];
        }
        for (Map.Entry<String, long[]> e : m.entrySet()) System.out.println("CLASS " + label + " " + e.getKey() + " n=" + e.getValue()[0] + " bytes=" + e.getValue()[1]);
    }

    static long sum(BitSet s, long[] size) { long t = 0; for (int i = s.nextSetBit(0); i >= 0; i = s.nextSetBit(i + 1)) t += size[i]; return t; }

    static BitSet reach(int n, int[] rs, int[] rt, List<Integer> roots, Set<Long> cut, boolean[] skip) {
        BitSet v = new BitSet(n); int[] st = new int[1024]; int sp = 0;
        for (int r : roots) { if (skip != null && skip[r]) continue; if (!v.get(r)) { v.set(r); if (sp == st.length) st = Arrays.copyOf(st, sp * 2); st[sp++] = r; } }
        while (sp > 0) {
            int x = st[--sp];
            for (int e = rs[x]; e < rs[x + 1]; e++) {
                int y = rt[e];
                if (v.get(y)) continue;
                if (skip != null && skip[y]) continue;
                if (cut != null && cut.contains(((long) x << 32) | y)) continue;
                v.set(y); if (sp == st.length) st = Arrays.copyOf(st, sp * 2); st[sp++] = y;
            }
        }
        return v;
    }

    static int find(long[] sid, int[] sidx, long id) { if (id == 0) return -1; int k = Arrays.binarySearch(sid, id); return k < 0 ? -1 : sidx[k]; }

    static void heap(int end) {
        while (b.position() < end) {
            int st = b.get() & 0xff;
            switch (st) {
                case 0xFF: roots.add(id()); break;
                case 0x01: roots.add(id()); id(); break;
                case 0x02: roots.add(id()); b.getInt(); b.getInt(); break;
                case 0x03: roots.add(id()); b.getInt(); b.getInt(); break;
                case 0x04: roots.add(id()); b.getInt(); break;
                case 0x05: roots.add(id()); break;
                case 0x06: roots.add(id()); b.getInt(); break;
                case 0x07: roots.add(id()); break;
                case 0x08: roots.add(id()); b.getInt(); b.getInt(); break;
                case 0x20: {
                    Cls c = new Cls(); c.id = id(); b.getInt(); c.sup = id(); c.loader = id(); id(); id(); id(); id(); b.getInt();
                    int cp = b.getShort() & 0xffff; for (int j = 0; j < cp; j++) { b.getShort(); int t = b.get(); b.position(b.position() + vsize(t)); }
                    int ns = b.getShort() & 0xffff; List<Long> sr = new ArrayList<>();
                    for (int j = 0; j < ns; j++) { id(); int t = b.get(); if (t == 2) sr.add(id()); else b.position(b.position() + vsize(t)); }
                    int nf = b.getShort() & 0xffff; c.ftypes = new int[nf]; c.fnames = new String[nf];
                    for (int j = 0; j < nf; j++) { long nid = id(); c.ftypes[j] = b.get(); c.fnames[j] = String.valueOf(nid); }
                    c.statics = sr.stream().mapToLong(Long::longValue).toArray();
                    classes.put(c.id, c); add(c.id, 3, 0, 0, 0);
                    break;
                }
                case 0x21: { long i = id(); b.getInt(); long cid = id(); int len = b.getInt(); add(i, 0, cid, b.position(), len); b.position(b.position() + len); break; }
                case 0x22: { long i = id(); b.getInt(); int n = b.getInt(); long acid = id(); add(i, 1, acid, b.position(), n); b.position(b.position() + n * idSize); break; }
                case 0x23: { long i = id(); b.getInt(); int n = b.getInt(); int t = b.get(); add(i, 2, t, b.position(), n); b.position(b.position() + n * esize(t)); break; }
                default: throw new IllegalStateException("sub-record 0x" + Integer.toHexString(st) + " at " + b.position());
            }
        }
    }
}
