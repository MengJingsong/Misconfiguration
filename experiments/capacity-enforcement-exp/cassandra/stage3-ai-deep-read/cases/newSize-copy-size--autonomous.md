# newSize (`RefCountedMemory.copy(long newSize)`) — verification solution  <!-- file: cases/newSize-copy-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place, read in place of "the if statement"): [`RefCountedMemory.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/RefCountedMemory.java#L60), `copy.put(0, this, 0, Math.min(size(), newSize));` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. `newSize` is a method argument, not a configured limit. No code path in the 5.0.9 tree calls `RefCountedMemory.copy`, so it has no effect on a running node. When the method is called directly, the `Math.min` at :60 only clamps how many bytes are copied into a buffer that has already been allocated at exactly `newSize` bytes (:59). It never limits an allocation. |
| Ground | (1) **Unreachable.** `RefCountedMemory` is used only by `SerializingCache`, which never calls `copy` (`SerializingCache.java:91-256`). Every `.copy(long)` call site in `src/java` has a static receiver type of `SafeMemory` (`SafeMemoryWriter.java:58`, `CompressionMetadata.java:368,418`), so neither the method nor its `Memory.copy` bridge dispatches here. (2) **Not a cap.** At :59 the method allocates `newSize` bytes with no check against any configured limit. The `min` at :60 is a bounds clamp that keeps `put` within both regions (`Memory.java:204-209`). Memory held by `RefCountedMemory` objects is capped elsewhere, by `row_cache_size` through Caffeine's `maximumWeight` (`SerializingCache.java:50-53`, `SerializingCacheProvider.java:33`). |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `newSize`, the parameter of `RefCountedMemory.copy(long newSize)`.
- **Kind:** runtime value, specifically a method argument chosen by a caller. It is not a configuration entry, a `-D` property or a constant.
- **Declaration:** first declared at [`RefCountedMemory.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/RefCountedMemory.java#L57).
- **Unit:** bytes.
- **Default:** none. Its value is whatever the caller passes.
- **How it is set:** it cannot be set by an operator (no yaml key, `-D` property or JMX attribute). The tree contains no caller at all (see A3), so in 5.0.9 it is never set by code either.
- **Restart:** not applicable.
- **The other operand:** `size()` (`Memory.java:220-224`) is the size of the source region. That size is fixed when the source is created, in production only at `SerializingCache.java:100` with `serializedSize`.

**A2. What it caps.**
- **Resource:** off-heap native memory. `RefCountedMemory` extends `Memory`, whose constructor calls `MemoryUtil.allocate(size)` → `Native.malloc` (`Memory.java:59-70`, `MemoryUtil.java:81-84`).
- **Quantity at the given line:** `Math.min(size(), newSize)` is the number of bytes copied from the source region into the new region.
- **What `newSize` does:** it is the size of the new allocation (:59) and an upper bound on the copy length (:60). The bound on the copy length is a memory-safety clamp, not a usage cap. Without it, `put` would overrun one region, and `checkBounds` (`Memory.java:197-201`) would assert when assertions are enabled.

**A3. Mechanism.**
1. `RefCountedMemory.copy(newSize)` (`RefCountedMemory.java:57`) runs `new RefCountedMemory(newSize)` (:59) → `Memory(long)` (`Memory.java:59-70`):
   - if `bytes <= 0` it throws `AssertionError` (:62-63);
   - otherwise it calls `Native.malloc(newSize)`;
   - if `peer == 0` (malloc failed) it throws `OutOfMemoryError` (:68-69).

   There is no comparison against any Cassandra limit. The only bounds are `> 0` and whether malloc succeeds.
2. The given line, [`RefCountedMemory.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/RefCountedMemory.java#L60), calls `copy.put(0, this, 0, Math.min(size(), newSize))`. `Memory.put` (`Memory.java:204-209`) bounds-checks both regions, then calls `unsafe.copyMemory`.
   - If `newSize < size()`, the copy is truncated to `newSize` bytes. The source keeps its full allocation until it is unreferenced.
   - If `newSize >= size()`, all `size()` bytes are copied and the tail `[size(), newSize)` is left uninitialised but still allocated.
   - Either way the allocation is exactly `newSize` bytes.
3. **No callers.** A text search for `RefCountedMemory` across the whole tree finds only `SerializingCache.java`, `RefCountedMemory.java` and one CHANGES.txt line; nothing in `test/`. `SerializingCache` creates instances (`:100`) and calls `reference`/`unreference` (`:56,113,154,162,179,184,201,206,219,223,240,245,247,255`), never `copy`.
4. **Virtual dispatch.** `RefCountedMemory.copy` is a covariant override of `Memory.copy` (`Memory.java:211-216`), so a call on a `Memory`-typed reference could dispatch here. The only `.copy(long)` calls on `Memory`-family objects in `src/java` have static type `SafeMemory`:
   - `SafeMemoryWriter.java:58`
   - `CompressionMetadata.java:368`
   - `CompressionMetadata.java:418`

   `SafeMemory` is a sibling subclass (`SafeMemory.java:27`), so none of them can reach `RefCountedMemory.copy`.
5. **Bypass and overshoot.** Because the method is dead code, every `RefCountedMemory` allocation in production goes through `SerializingCache.serialize` (`:91-117`):
   - size `serializedSize`, refused only if it exceeds `Integer.MAX_VALUE` (:94-95);
   - malloc failure turns into a dropped cache put (:102-105, :169-170).

   Accounting is by Caffeine weight, which is `value.size()` (`SerializingCache.java:67-75`), against `maximumWeight(capacity)` (:52). The capacity is `row_cache_size` × 1 MiB (`SerializingCacheProvider.java:33`, `DatabaseDescriptor.java:3916-3919`). If `copy` were ever called, its allocation would never enter that accounting: the copy is a new object that is not in the cache.

**A4. Other consumers.** Other users of native memory that are outside any `newSize`:
- **Identical copy pattern:** `Memory.copy` and `SafeMemory.copy` (`Memory.java:211-216`, `SafeMemory.java:70-75`), used by `SafeMemoryWriter.resizeTo` (`:51-66`) and by `CompressionMetadata` offset growth (`:368`, `:418`).
- **Other caches and pools:** the OHC row cache (the default `row_cache_class_name`, `Config.java:472`), the chunk cache and buffer pool (`file_cache_size`), networking buffers (`networking_cache_size`), off-heap memtables when `memtable_allocation_type` is an off-heap type, and bloom filters and index summaries.
- **Sentinels:** in-flight `RefCountedMemory` sentinels from `SinglePartitionReadCommand.java:561`. These go through `SerializingCache.putIfAbsent` and are weighed.

**A5. Evidence beyond the source.**
- `CHANGES.txt:4927`, "Use AtomicIntegerFieldUpdater in RefCountedMemory (CASSANDRA-6278)": <https://issues.apache.org/jira/browse/CASSANDRA-6278>. This only shows the class's history; it does not concern `copy`.
- `conf/cassandra.yaml:545-564` documents `row_cache_class_name` / `SerializingCacheProvider` and `row_cache_size` (default `0MiB`, row cache disabled).
- glibc `mallopt(3)`: the `M_MMAP_THRESHOLD` and `MALLOC_MMAP_THRESHOLD_` environment variable. These are relied on for the RSS readings: <https://man7.org/linux/man-pages/man3/mallopt.3.html>.
- Linux `proc(5)` `VmRSS`/`RssAnon`: <https://man7.org/linux/man-pages/man5/proc.5.html>.
- Byteman 4.0.20 programmer's guide (rule syntax, `traceln`): <https://downloads.jboss.org/byteman/4.0.20/byteman-programmers-guide.html>.

No git history was available in the source copy, so none was consulted.

## B. Verification solution

**B1. Claim under test.** `newSize` at `RefCountedMemory.java:57-60` does not cap Cassandra 5.0.9's memory use. The claim has two parts, and each tier tests both:
- **(a) Never invoked.** On a running node with the `SerializingCache` row cache under load, `RefCountedMemory.copy` is never called (0 invocations). The node's `RefCountedMemory` off-heap use follows `row_cache_size` instead.
- **(b) Not a cap when called.** When the method is called directly, the allocation equals `newSize` for every value the allocator grants, with no Cassandra-level ceiling. The `min` at :60 changes only the number of bytes copied, which is `min(size(), newSize)`.

### B2. Unit tier

**B2a. Environment and build.**
- **Node and tools:** Linux node, JDK 11 (`java -version` reports 11.x), Apache Ant ≥ 1.10.
- **Source copy:** copy the pristine tree to local disk and build there, never in the shared tree:
  ```
  mkdir -p /mydata/o145 && rsync -a ~/cassandra-5.0.9/ /mydata/o145/cassandra/
  cd /mydata/o145/cassandra && ant -Dno-checkstyle=true jar build-test
  ```
  The `build-test` target pulls test deps, including Byteman 4.0.20 / BMUnit (`.build/parent-pom-template.xml:40`, `.build/cassandra-deps-template.xml:336-349`).
- **Test source:** `/mydata/o145/cassandra/test/unit/org/apache/cassandra/cache/RefCountedMemoryCopyO145Test.java` (code in B2e).
- **JVM:** default `ant testsome` JVM options. Set the environment variable `MALLOC_MMAP_THRESHOLD_=131072` for the run. Fixing the threshold turns off glibc's dynamic threshold, so every allocation ≥ 128 KiB is its own `mmap`, committed lazily and returned at free, which makes RSS deltas exact. The forked JUnit JVM inherits the environment.

**B2b. Knobs.**
- **Main knob:** `newSize` passed to `copy`. The source region is fixed at `S` = 128 MiB. Values, chosen to straddle `S` and then go far past it and past physical memory:

  | `newSize` | Purpose |
  |---|---|
  | 16 MiB | `< S`, truncating copy |
  | 64 MiB | `< S`, truncating copy |
  | 128 MiB | `= S` |
  | 512 MiB | `> S`, padded allocation |
  | 4096 MiB | `≫ S`, no Cassandra ceiling |
  | 0 | lower guard (`Memory.java:62`) |
  | 1 TiB (`1L<<40`) | above RAM+swap: only malloc refuses, under `vm.overcommit_memory=0`; check with `cat /proc/sys/vm/overcommit_memory`. If it is `1`, skip this value and note it. |

  All values are set in code.
- **Positive-control knob:** `SerializingCache` capacity `C` ∈ {32 MiB, 128 MiB}, a cap known to bind on `RefCountedMemory` usage.

**B2c. Workload.**
- **Part 1, direct copy:** fill a 128 MiB source with `0x11`, call `copy(n)` for each `n`, verify the copied prefix, touch the whole copy with `setMemory(0, n, 0x5A)`, then `unreference()` it. The value at :60 is reached whenever `n ≤ S` (copy length = `n`) and passed whenever `n > S` (copy length stays `S`). 4096 MiB is 32 × `S`.
- **Part 2, positive control:** `SerializingCache<Integer, byte[]>` with a 4-byte-length-prefixed `byte[]` serializer and the default size weigher (`SerializingCache.java:67-75`).
  - Put 512 distinct keys with 1 MiB values: 512 × (1 MiB + 4 B) ≈ 512 MiB of demand, against `C` = 32 MiB or 128 MiB.
  - The cap must evict, holding about `⌊C / (1 MiB + 4)⌋` entries: 31 or 127.
  - A BMUnit rule counts any `RefCountedMemory.copy` call during part 2.

**B2d. Observables and instruments.**
- **Allocation:** `c.size()` (`Memory.java:220-224`), the exact malloc request.
- **Copy length:** compute `min(S, n)`. Check the byte at `min(S, n) - 1` (expect `0x11`).
- **Process native footprint:** `VmRSS` from `/proc/self/status`, in KiB, read
  - before `copy`,
  - after `copy` (only the copied pages are committed),
  - after the touch (all `n` bytes committed),
  - after `unreference` (munmapped).
- **Positive control:** `cache.weightedSize()`, `cache.size()`, peak `VmRSS` over the 512 puts (with a printout every 64 puts), and the Byteman counter `COPIES`.
- **Output:** every reading is printed as a line starting `O145 ` to stdout. Ant captures it in `build/test/output/TEST-org.apache.cassandra.cache.RefCountedMemoryCopyO145Test.xml`.
- **Not directly observable:** what malloc does internally. RSS is the proxy, and it is noisy by a few MiB from JIT and GC threads. That noise is small next to the ≥ 16 MiB steps.

**B2e. Procedure.**
1. Make the copy and build (B2a).
2. Write the test:
   ```java
   package org.apache.cassandra.cache;

   import java.io.IOException;
   import java.nio.file.*;
   import java.util.concurrent.atomic.AtomicLong;
   import org.junit.*;
   import org.junit.runner.RunWith;
   import org.jboss.byteman.contrib.bmunit.BMRule;
   import org.jboss.byteman.contrib.bmunit.BMUnitRunner;
   import org.apache.cassandra.config.DatabaseDescriptor;
   import org.apache.cassandra.io.ISerializer;
   import org.apache.cassandra.io.util.*;
   import static org.junit.Assert.*;

   @RunWith(BMUnitRunner.class)
   public class RefCountedMemoryCopyO145Test
   {
       static final long MiB = 1L << 20;
       public static final AtomicLong COPIES = new AtomicLong();

       @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

       static long rssKiB() throws IOException
       {
           for (String l : Files.readAllLines(Paths.get("/proc/self/status")))
               if (l.startsWith("VmRSS:")) return Long.parseLong(l.replaceAll("\\D+", ""));
           throw new IllegalStateException();
       }

       @Test
       public void copyAllocatesNewSize() throws Exception
       {
           long S = 128 * MiB;
           RefCountedMemory src = new RefCountedMemory(S);
           src.setMemory(0, S, (byte) 0x11);
           for (long n : new long[]{ 16 * MiB, 64 * MiB, 128 * MiB, 512 * MiB, 4096 * MiB })
           {
               System.gc(); Thread.sleep(200);
               long r0 = rssKiB();
               RefCountedMemory c = src.copy(n);
               long r1 = rssKiB();
               long copied = Math.min(S, n);
               assertEquals(0x11, c.getByte(copied - 1));
               long size = c.size();
               c.setMemory(0, n, (byte) 0x5A);
               long r2 = rssKiB();
               c.unreference();
               long r3 = rssKiB();
               System.out.printf("O145 unit n=%d size=%d copied=%d dRssCopyKiB=%d dRssTouchKiB=%d dRssFreeKiB=%d%n",
                                 n, size, copied, r1 - r0, r2 - r0, r3 - r0);
               assertEquals(n, size);
           }
           try { src.copy(0); fail(); } catch (AssertionError e) { System.out.println("O145 unit n=0 AssertionError"); }
           try { RefCountedMemory h = src.copy(1L << 40); System.out.println("O145 unit n=1TiB size=" + h.size()); h.unreference(); }
           catch (OutOfMemoryError e) { System.out.println("O145 unit n=1TiB OutOfMemoryError"); }
           src.unreference();
       }

       static final ISerializer<byte[]> BYTES = new ISerializer<byte[]>()
       {
           public void serialize(byte[] b, DataOutputPlus out) throws IOException { out.writeInt(b.length); out.write(b); }
           public byte[] deserialize(DataInputPlus in) throws IOException { byte[] b = new byte[in.readInt()]; in.readFully(b); return b; }
           public long serializedSize(byte[] b) { return 4 + b.length; }
       };

       @Test
       @BMRule(name = "o145-count-copy",
               targetClass = "org.apache.cassandra.cache.RefCountedMemory",
               targetMethod = "copy(long)",
               targetLocation = "AT ENTRY",
               action = "org.apache.cassandra.cache.RefCountedMemoryCopyO145Test.COPIES.incrementAndGet()")
       public void positiveControlCacheCapBinds() throws Exception
       {
           byte[] v = new byte[(int) MiB];
           java.util.Arrays.fill(v, (byte) 0x33);
           for (long C : new long[]{ 32 * MiB, 128 * MiB })
           {
               COPIES.set(0);
               System.gc(); Thread.sleep(200);
               long r0 = rssKiB(), peak = 0;
               SerializingCache<Integer, byte[]> cache = SerializingCache.create(C, BYTES);
               for (int k = 0; k < 512; k++)
               {
                   cache.put(k, v);
                   peak = Math.max(peak, rssKiB() - r0);
                   if (k % 64 == 63)
                       System.out.printf("O145 ctl C=%d k=%d entries=%d weighted=%d dRssKiB=%d%n",
                                         C, k, cache.size(), cache.weightedSize(), rssKiB() - r0);
               }
               System.out.printf("O145 ctl C=%d final entries=%d weighted=%d peakDRssKiB=%d copies=%d%n",
                                 C, cache.size(), cache.weightedSize(), peak, COPIES.get());
               assertTrue(cache.weightedSize() <= C);
               assertEquals(0, COPIES.get());
               cache.clear();
           }
       }
   }
   ```
   If `@RunWith(BMUnitRunner.class)` fails to load the agent in this build, add `-Dtest.jvm.args=-Djdk.attach.allowAttachSelf=true`. That is the same agent-loading mechanism `test/unit/org/apache/cassandra/dht/BootStrapperTest.java:48-50` relies on.
3. Static reachability check, run in the build copy:
   ```
   cd /mydata/o145/cassandra
   find build/classes -name '*.class' > /mydata/o145/classes.txt
   xargs -a /mydata/o145/classes.txt javap -c -p 2>/dev/null > /mydata/o145/javap.txt
   grep -c 'Method org/apache/cassandra/cache/RefCountedMemory.copy:' /mydata/o145/javap.txt
   grep -c 'Method org/apache/cassandra/io/util/Memory.copy:' /mydata/o145/javap.txt
   grep -c 'Method org/apache/cassandra/io/util/SafeMemory.copy:' /mydata/o145/javap.txt
   ```
   The bridge method inside `RefCountedMemory.class` prints its self-call without the class prefix (`Method copy:(J)…`), so it is not counted.
4. Run:
   ```
   cd /mydata/o145/cassandra
   MALLOC_MMAP_THRESHOLD_=131072 ant testsome -Dtest.name=org.apache.cassandra.cache.RefCountedMemoryCopyO145Test
   grep -o 'O145 [^<]*' build/test/output/TEST-org.apache.cassandra.cache.RefCountedMemoryCopyO145Test.xml
   ```
5. Check nothing is left: `pgrep -f RefCountedMemoryCopyO145Test` should be empty.

**B2f. Predictions** (stated before any run).

Part 1, with `S` = 128 MiB:

| `n` | `size` | `copied` | `dRssCopy` | `dRssTouch` | `dRssFree` |
|---|---|---|---|---|---|
| 16 MiB | 16 MiB | 16 MiB | ≈ +16 MiB | ≈ +16 MiB | ≈ 0 |
| 64 MiB | 64 MiB | 64 MiB | ≈ +64 MiB | ≈ +64 MiB | ≈ 0 |
| 128 MiB | 128 MiB | 128 MiB | ≈ +128 MiB | ≈ +128 MiB | ≈ 0 |
| 512 MiB | 512 MiB | 128 MiB | ≈ +128 MiB | ≈ +512 MiB | ≈ 0 |
| 4096 MiB | 4096 MiB | 128 MiB | ≈ +128 MiB | ≈ +4096 MiB | ≈ 0 |

- RSS deltas are within ±8 MiB.
- `n = 0`: `AssertionError`.
- `n = 1 TiB`: `OutOfMemoryError` under overcommit mode 0. No Cassandra-specific check is reported anywhere.
- The allocation always equals `n`. Nothing at :60 lowers it.

Part 2:
- `C` = 32 MiB: final entries = 31 and weighted ≤ 32 MiB (31 × 1,048,580 B ≈ 31.0 MiB); peak `dRss` ≈ 32-40 MiB.
- `C` = 128 MiB: entries = 127; peak `dRss` ≈ 128-136 MiB.
- In both cases `copies` = 0 and RSS does not approach the 512 MiB of demand.

Static check (step 3): counts are 0, 0 and ≥ 3 (the three `SafeMemory.copy` sites).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size == n` for every granted `n`, including `n ≫ S`, `dRssTouch ≈ n`, and copy length `= min(S,n)` | (b) confirmed: `newSize` sets the allocation; :60 clamps only the copy. |
| `size < n` for some `n`, or `copy` refuses a large `n` with a Cassandra-level error (not malloc's OOME), or RSS after touch stays below `n` | Usage follows a cap tied to :60. **Claim refuted.** |
| Static count of `RefCountedMemory.copy` or `Memory.copy` call sites > 0 | A caller exists, so (a) is wrong. Trace that caller before concluding. **Claim refuted** as stated. |
| Part 2: `copies` = 0 while `weightedSize ≤ C` and peak RSS ≈ C moves with `C` (32 → 128 MiB moves peak by ≈ 96 MiB) | The positive control moved while `copy` stayed silent. **Claim confirmed.** |
| Part 2: `copies` > 0 | `SerializingCache` reaches `copy`. **Claim refuted.** |
| Part 2: peak RSS does not move with `C`, or `weightedSize` exceeds `C` by more than one entry | Control did not bind, or the instrument is blind. **Not confirmed.** Re-run with `MALLOC_MMAP_THRESHOLD_` set and check `VmRSS` parsing. |
| Part 1: RSS deltas ≈ 0 even after the touch | Instrument blind (env var not inherited, or pages already resident). **Not confirmed.** |

**B2h. Controls.**
- The touch step proves that RSS sees native allocations of the size under test.
- Part 2 proves the same instruments register a known cap.
- `System.gc()` before each step and a fixed mmap threshold reduce heap and allocator noise.
- Varying `n` on both sides of `S` separates "allocation follows `newSize`" from "allocation follows the source size".
- The static bytecode scan covers all compiled classes, including tools, so reachability does not rest on a text grep alone.

### B3. Cluster tier

**B3a. Environment and build.**
- **Topology:** one node on the local Linux machine, the minimum needed. The claim concerns a node-local method with no inter-node path.
- **Build:** use the B2a build copy `/mydata/o145/cassandra`, plus `ant stress-build` for `tools/bin/cassandra-stress`.
- **Byteman jar:** `BM=$(find /mydata/o145/cassandra/build -name 'byteman-4.0.20.jar' | head -1)`.
- **Directories:** data, commit log, hints, saved caches and logs go under `/mydata/o145/node/`, on local disk (check `df -h /mydata`; the run needs ≤ 6 GiB).
- **Configuration changes** in `/mydata/o145/cassandra/conf/cassandra.yaml` (the copy):
  ```
  cluster_name: o145
  listen_address: 127.0.0.1
  rpc_address: 127.0.0.1
  seed_provider: [{class_name: org.apache.cassandra.locator.SimpleSeedProvider, parameters: [{seeds: "127.0.0.1:17145"}]}]
  storage_port: 17145
  native_transport_port: 19145
  data_file_directories: [/mydata/o145/node/data]
  commitlog_directory: /mydata/o145/node/commitlog
  hints_directory: /mydata/o145/node/hints
  saved_caches_directory: /mydata/o145/node/saved_caches
  cdc_raw_directory: /mydata/o145/node/cdc
  row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider
  row_cache_size: 64MiB        # varied, B3b
  row_cache_save_period: 0s
  file_cache_size: 32MiB
  disk_access_mode: standard
  ```
  Edit these keys in place rather than appending duplicates. The non-default ports avoid other users of this machine. `file_cache_size: 32MiB` and `disk_access_mode: standard` keep the chunk cache and mmapped reads out of the reading.
- **JMX port:** edit the copied `conf/cassandra-env.sh` with `sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/'`.
- **Heap:** `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. `-XX:+AlwaysPreTouch` is already on (`conf/jvm-server.options:128`), so the heap contributes a constant to RSS.
- **Byteman agent:** `JVM_EXTRA_OPTS="-javaagent:$BM=script:/mydata/o145/rcm.btm"` (`conf/cassandra-env.sh:307`), with `/mydata/o145/rcm.btm` containing:
  ```
  RULE o145 RefCountedMemory.copy
  CLASS org.apache.cassandra.cache.RefCountedMemory
  METHOD copy(long)
  AT ENTRY
  IF true
  DO traceln("O145 RCM.copy newSize=" + $1)
  ENDRULE

  RULE o145 RefCountedMemory alloc
  CLASS org.apache.cassandra.cache.RefCountedMemory
  METHOD <init>(long)
  AT EXIT
  IF true
  DO traceln("O145 RCM.alloc " + $1)
  ENDRULE
  ```

**B3b. Knobs.**
- **No setting for `newSize`.** It cannot be set (A1), so the cluster tier varies the inputs that would drive any `RefCountedMemory` copy if one existed:
  - **`row_cache_size`** ∈ {`0MiB`, `64MiB`, `512MiB`}, set in yaml with a restart per value. `0MiB` selects `NopCacheProvider` (`CacheService.java:146-147`) and serves as the no-`RefCountedMemory` baseline. 64 MiB and 512 MiB are both well below the 2 GiB of cacheable data, so both bind.
  - **Runtime resize:** in the 512 MiB run, after the read phase, run `nodetool -p 17199 setcachecapacity 100 64 50` (key, row and counter caches, in MiB). That shrinks the row cache to 64 MiB through `SerializingCache.setCapacity` (`:124-127`). A resize is the obvious place a copy could be used.
- **Partition size:** fixed at 64 KiB, so each cache entry exceeds the default glibc mmap threshold.

**B3c. Workload.**
- **Profile:** `cassandra-stress` user profile `/mydata/o145/blobs.yaml`:
  ```yaml
  keyspace: o145
  keyspace_definition: CREATE KEYSPACE o145 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  table: blobs
  table_definition: |
    CREATE TABLE blobs (pk bigint PRIMARY KEY, v blob)
      WITH caching = {'keys':'ALL','rows_per_partition':'ALL'} AND compression = {'enabled':false}
  columnspec:
    - name: pk
      population: seq(1..32768)
    - name: v
      size: fixed(65536)
  insert:
    partitions: fixed(1)
    batchtype: UNLOGGED
  queries:
    read1:
      cql: select * from blobs where pk = ?
      fields: samerow
  ```
- **Size:** 32,768 partitions × 64 KiB = 2 GiB of data, about 2 GiB on disk uncompressed.
- **Read path:** each first read of a partition is a cache miss. It does `putIfAbsent(sentinel)`, a 9-byte `RefCountedMemory` (`SinglePartitionReadCommand.java:561`, `SerializingCacheProvider.java:59-67`), then `replace(sentinel, partition)`, a `RefCountedMemory` of about 64 KiB plus row overhead (`:608`).
- **Cache demand:** 2 GiB of cacheable data against 64 MiB (about 1,000 entries) or 512 MiB (about 8,000 entries), so the cap is passed by 4× to 32×.
- **Duration:** about 2 minutes of insert and 2 × 2 minutes of reads per value.

**B3d. Observables and instruments.**
- **Usage-side:** `nodetool -p 17199 info`, line `Row Cache : entries N, size X, capacity Y …`. Here `size` is Caffeine's `weightedSize()`, the sum of `RefCountedMemory.size()`.
- **Actual resource:** `RssAnon` (anonymous RSS, which excludes file-backed pages) from `/proc/$PID/status`, sampled every 5 s by a loop that appends to `/mydata/o145/run-<C>/rss.log`:
  ```
  while kill -0 $PID 2>/dev/null; do echo "$(date +%s) $(grep RssAnon /proc/$PID/status)"; sleep 5; done
  ```
- **Invocations:** `grep -c 'O145 RCM.copy' stdout.log` is the number of `copy` calls. For `RCM.alloc`, `grep -c` gives the count and an awk sum of `$3` gives the bytes. `bin/cassandra -f` sends Byteman `traceln` output to stdout, which is redirected to `/mydata/o145/run-<C>/stdout.log`.
- **Not directly observable:** per-object native residency. glibc may keep freed arena chunks for entries near the dynamic threshold, so RSS may plateau rather than fall after eviction. Predictions are therefore on the peak and plateau, not on a drop.

**B3e. Procedure.** For each `C` in {0, 64, 512} (MiB):
1. Prepare the directories:
   ```
   rm -rf /mydata/o145/node
   mkdir -p /mydata/o145/node /mydata/o145/run-$C
   ```
   Set `row_cache_size: ${C}MiB` in the copied `conf/cassandra.yaml`.
2. Start the node:
   ```
   cd /mydata/o145/cassandra
   MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="-javaagent:$BM=script:/mydata/o145/rcm.btm" \
     bin/cassandra -f -p /mydata/o145/run-$C/pid > /mydata/o145/run-$C/stdout.log 2>&1 &
   ```
   Wait until `bin/nodetool -p 17199 status` shows `UN`. Then set `PID=$(cat /mydata/o145/run-$C/pid)`, start the RSS sampler (B3d) in the background, and record the baseline `RssAnon`.
3. Check the log: `grep -i 'Initializing row cache' logs/system.log` should show capacity `C`.
4. Insert:
   ```
   tools/bin/cassandra-stress user profile=/mydata/o145/blobs.yaml "ops(insert=1)" n=32768 \
     -pop seq=1..32768 -rate threads=8 -node 127.0.0.1 -port native=19145 jmx=17199
   ```
   Then run `bin/nodetool -p 17199 flush o145`, wait 30 s and record `RssAnon` (the post-insert baseline).
5. Read twice:
   ```
   tools/bin/cassandra-stress user profile=/mydata/o145/blobs.yaml "ops(read1=1)" n=65536 \
     -pop seq=1..32768 -rate threads=8 -node 127.0.0.1 -port native=19145 jmx=17199
   ```
   After each pass record `nodetool info | grep 'Row Cache'` and `RssAnon`.
6. Only for `C`=512: run `bin/nodetool -p 17199 setcachecapacity 100 64 50`, run the read phase once more, and record the same readings.
7. Count `O145 RCM.copy` and `O145 RCM.alloc` lines in `stdout.log`, and the sum of `alloc` sizes.
8. Stop the node: `bin/nodetool -p 17199 drain; kill $(cat /mydata/o145/run-$C/pid)`. Wait for exit. Stop the sampler and the stress clients. `pgrep -af 'o145|CassandraDaemon|cassandra-stress'` should show none of this run's PIDs.

**B3f. Predictions** (stated before any run).

| `C` | Row Cache size after reads | `RssAnon` growth (post-insert → read plateau) | `RCM.alloc` count | `RCM.copy` count |
|---|---|---|---|---|
| 0 | 0 entries | ≈ 0 (± 50 MiB of JVM noise) | 0 | 0 |
| 64 MiB | ≤ 64 MiB (about 1,000 entries) | ≈ +64 MiB, ≤ +150 MiB | ≥ 65,536 (sentinel and value per miss) | 0 |
| 512 MiB | ≤ 512 MiB (about 7,900 entries) | ≈ +512 MiB, ≤ +620 MiB, and about 400-500 MiB above the 64 MiB run | ≥ 65,536 | 0 |

- **After the shrink in the 512 MiB run:** Row Cache size ≤ 64 MiB. `RCM.copy` stays 0: the shrink evicts, it does not copy. RSS may stay at its plateau (glibc retention) but must not grow.
- **Relation:** usage tracks `row_cache_size`. The `RCM.copy` count is 0 in every run, so `newSize` never takes a value on the node.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `RCM.copy` count > 0 in any run | A runtime path reaches :60. **Claim (a) refuted**; record the `newSize` values and the caller (add `traceStack()` to the rule) before anything else. |
| `RCM.copy` = 0, Row Cache size ≤ `C`, and the `RssAnon` plateau moves with `C` (0 → 64 → 512 MiB ⇒ ≈ +0 / +64 / +512 MiB) | The positive control moved while `newSize` was never exercised. **Claim confirmed:** off-heap `RefCountedMemory` use follows `row_cache_size`, not `newSize`. |
| `RCM.alloc` = 0 in the 64 MiB and 512 MiB runs | The `SerializingCache` path was not exercised: wrong `row_cache_class_name`, or `caching` not applied. **Not confirmed;** fix the configuration and re-run. |
| `RssAnon` plateau does not differ between 64 MiB and 512 MiB although Row Cache size does | The instrument is blind to these allocations, or glibc behaves differently than assumed. **Not confirmed** for the resource half. The `RCM.copy` = 0 half still stands. |
| Row Cache size > `C` by more than one entry, or `RssAnon` growth far above `C` + 150 MiB | The row cache cap is leaky, which is a separate finding. It does not change the `newSize` claim unless `RCM.copy` > 0. |

**B3h. Controls.**
- The `C`=0 run gives the node's own growth without `RefCountedMemory` (`NopCacheProvider`).
- The `RCM.alloc` count shows the class is being exercised, so `RCM.copy` = 0 is not a vacuous zero.
- The runtime shrink exercises the one resize path that could plausibly copy.
- `disk_access_mode: standard` and `RssAnon` keep mmapped sstable pages out of the reading. The small `file_cache_size` and flushed memtables keep the other off-heap consumers (A4) small and constant across runs.

**B4. Risks and cleanup.**
- **Disk:** everything is under `/mydata/o145/` on local disk; peak use is about 6 GiB (2 GiB of sstables, about 2 GiB of commit log, and the build). Nothing is written to `~/cassandra-5.0.9` or shared storage.
- **Unit tier memory:** the 4096 MiB touch needs 4 GiB of free RAM. Skip that value if `MemAvailable` in `/proc/meminfo` is below 16 GiB. The 1 TiB request is refused by malloc and never committed.
- **Processes:** the unit tier's JUnit fork exits with Ant. In the cluster tier, stop the node with `drain` + `kill`, kill the RSS sampler loop and any `cassandra-stress` JVMs. Verify with `pgrep -af 'o145|CassandraDaemon|cassandra-stress'` that none of this run's processes remain.
- **Ports:** 17145, 19145 and 17199 are used to avoid colliding with other nodes on the machine.
- **Cleanup:** `rm -rf /mydata/o145/node /mydata/o145/run-*`. Remove `/mydata/o145/cassandra` when stage 4 is done.

## C. Sources read

- ~/writeup-ext/playbook-autonomous.md
- ~/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cache/RefCountedMemory.java
- src/java/org/apache/cassandra/cache/SerializingCache.java
- src/java/org/apache/cassandra/cache/SerializingCacheProvider.java
- src/java/org/apache/cassandra/io/util/Memory.java
- src/java/org/apache/cassandra/io/util/SafeMemory.java (copy, lines 27-75)
- src/java/org/apache/cassandra/io/util/SafeMemoryWriter.java (lines 40-70)
- src/java/org/apache/cassandra/io/compress/CompressionMetadata.java (lines 368, 418, by search)
- src/java/org/apache/cassandra/io/ISerializer.java
- src/java/org/apache/cassandra/utils/memory/MemoryUtil.java (lines 78-90)
- src/java/org/apache/cassandra/service/CacheService.java (lines 112-160)
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (lines 505-620)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (row cache uses, by search)
- src/java/org/apache/cassandra/config/Config.java (lines 472-474)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 3913-3925)
- src/java/org/apache/cassandra/tools/nodetool/Info.java (lines 104-106)
- test/unit/org/apache/cassandra/cache/CacheProviderTest.java (by search)
- test/unit/org/apache/cassandra/dht/BootStrapperTest.java (BMUnit imports)
- conf/cassandra.yaml (row cache, file cache, ports, memtable allocation)
- conf/cassandra-env.sh (JMX_PORT, MALLOC_ARENA_MAX, JVM_EXTRA_OPTS, heap)
- conf/jvm-server.options (AlwaysPreTouch)
- build.xml (test targets, stress-build), .build/parent-pom-template.xml, .build/cassandra-deps-template.xml (Byteman)
- CHANGES.txt (line 4927)
- https://issues.apache.org/jira/browse/CASSANDRA-6278
- https://man7.org/linux/man-pages/man3/mallopt.3.html
- https://man7.org/linux/man-pages/man5/proc.5.html
- https://downloads.jboss.org/byteman/4.0.20/byteman-programmers-guide.html

## D. Stage-4 feedback

none yet
