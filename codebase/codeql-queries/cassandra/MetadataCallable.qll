import java

class MetadataCallable extends Callable {
    MetadataCallable() {
        this instanceof Constructor and 
        (
            (
                this.getName() = "BufferCell" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "BufferCell")
            )
            or (
                this.getName() = "BTreeRow" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "BTreeRow")
            ) 
            or (
                this.getName() = "EncodingStats" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "EncodingStats")
            ) 
            or (
                this.getName() = "BTreePartitionData" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.partitions", "BTreePartitionData")
            ) 
            or (
                this.getName() = "AtomicBTreePartition" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.partitions", "AtomicBTreePartition")
            ) 
            or (
                this.getName() = "LivenessInfo" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db", "LivenessInfo")
            ) 
            or (
                this.getName() = "BufferDecoratedKey" and
                this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db", "BufferDecoratedKey")
            )
        )
    }
}