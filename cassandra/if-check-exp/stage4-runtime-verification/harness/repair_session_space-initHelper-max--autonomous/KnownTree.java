// Stage-4 harness (repair_session_space-initHelper-max--autonomous): known-answer object for the histogram instrument (C4).
// Builds one on-heap Murmur3 MerkleTree with maxsize 2^k (init(), so 2^k OnHeapLeaf and 2^k-1 OnHeapInner), prints READY, holds it.
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.utils.MerkleTree;

public class KnownTree
{
    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.clientInitialization();
        int k = Integer.parseInt(a[0]);
        Token min = Murmur3Partitioner.instance.getMinimumToken();
        MerkleTree t = new MerkleTree(Murmur3Partitioner.instance, new Range<>(min, min), 126, 1L << k);
        t.init();
        System.out.println("READY size=" + t.size());
        Thread.sleep(Long.parseLong(a[1]));
        System.out.println("END " + t.size());
    }
}
