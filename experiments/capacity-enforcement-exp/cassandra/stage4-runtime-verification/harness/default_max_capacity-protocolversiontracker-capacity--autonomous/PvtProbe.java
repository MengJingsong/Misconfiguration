package org.apache.cassandra.transport;
import java.lang.reflect.*; import java.net.InetAddress; import java.util.*;
import com.github.benmanes.caffeine.cache.Cache;
public class PvtProbe {
  public static void main(String[] a) throws Exception {
    int cap = Integer.parseInt(a[0]); int n = Integer.parseInt(a[1]);
    ProtocolVersionTracker pvt;
    if (cap == 100) pvt = new ProtocolVersionTracker();
    else { Constructor<ProtocolVersionTracker> c = ProtocolVersionTracker.class.getDeclaredConstructor(int.class);
           c.setAccessible(true); pvt = c.newInstance(cap); }
    Field f = ProtocolVersionTracker.class.getDeclaredField("clientsByProtocolVersion"); f.setAccessible(true);
    Map<ProtocolVersion, Cache<?,?>> caches = (Map) f.get(pvt);
    long h0 = heapAfterGc();
    for (int i = 0; i < n; i++) {
      pvt.addConnection(addr(i), ProtocolVersion.V4);
      if ((i & 0xFFF) == 0) { long raw = caches.get(ProtocolVersion.V4).estimatedSize(); if (raw > maxRaw) maxRaw = raw; }
    }
    caches.values().forEach(Cache::cleanUp);
    long h1 = heapAfterGc();
    System.out.printf("cap=%d n=%d maxRawBeforeCleanup=%d V4.estimatedSize=%d V4.getAll=%d all=%d heapDeltaBytes=%d%n",
        cap, n, maxRaw, caches.get(ProtocolVersion.V4).estimatedSize(), pvt.getAll(ProtocolVersion.V4).size(),
        pvt.getAll().size(), h1 - h0);
    for (ProtocolVersion v : new ProtocolVersion[]{ProtocolVersion.V3, ProtocolVersion.V5, ProtocolVersion.V6})
      for (int i = 0; i < n / 2; i++) pvt.addConnection(addr(i + 20_000_000), v);
    caches.values().forEach(Cache::cleanUp);
    for (ProtocolVersion v : ProtocolVersion.values()) System.out.printf("%s=%d ", v, pvt.getAll(v).size());
    System.out.printf("total=%d%n", pvt.getAll().size());
    System.out.println(pvt.hashCode()); // keep pvt reachable until here
  }
  static long maxRaw = 0;
  static InetAddress addr(int i) throws Exception { return InetAddress.getByAddress(new byte[]{10,(byte)(i>>16),(byte)(i>>8),(byte)i}); }
  static long heapAfterGc() throws Exception { for (int k = 0; k < 3; k++) { System.gc(); Thread.sleep(200); }
    Runtime r = Runtime.getRuntime(); return r.totalMemory() - r.freeMemory(); }
}
