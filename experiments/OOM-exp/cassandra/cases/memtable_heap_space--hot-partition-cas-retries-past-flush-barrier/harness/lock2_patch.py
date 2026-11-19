"""B18 I2 patch (design §2.8), applied to a copy of AtomicBTreePartition.java. usage: python3 -I lock2_patch.py <file>"""
import sys
p = sys.argv[1]
s = open(p).read()
old_field = "    private volatile BTreePartitionData ref;\n"
assert s.count(old_field) == 1
s = s.replace(old_field, old_field + "\n    // B18 I2 (diagnostic): an exclusive per-partition lock for the waste tracker's pessimistic mode\n"
              "    static final class B18Lock extends java.util.concurrent.locks.ReentrantLock {}\n"
              "    final B18Lock b18Lock = new B18Lock();\n")
old = """                    if (shouldLock)
                    {
                        synchronized (this)
                        {
                            if (tryUpdateData(update))
                                return this;
                        }
                    }"""
new = """                    if (shouldLock)
                    {
                        // B18 I2: exclusive per-partition lock; give up waiting (attempt unlocked) only when the write's
                        // op group is blocking a flush barrier (CASSANDRA-15367 4.0 semantics)
                        boolean locked = false;
                        try
                        {
                            while (!(locked = b18Lock.tryLock(1, java.util.concurrent.TimeUnit.MILLISECONDS)))
                                if (writeOp.isBlocking())
                                    break;
                        }
                        catch (InterruptedException e)
                        {
                            Thread.currentThread().interrupt();
                        }
                        try
                        {
                            if (tryUpdateData(update))
                                return this;
                        }
                        finally
                        {
                            if (locked)
                                b18Lock.unlock();
                        }
                    }"""
assert s.count(old) == 1
s = s.replace(old, new)
open(p, 'w').write(s)
print('patched')
