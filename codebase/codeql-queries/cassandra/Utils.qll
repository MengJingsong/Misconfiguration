import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

Callable getCallee(Call call) {
    (
        result.isStatic() and
        call.getCallee() = result and
        call.getCaller().calls(result)
    )
    or (
        (not result.isStatic()) and
        call.getCallee().getName() = result.getName() and
        call.getCaller().callsImpl(result)
    )
}

predicate dispatchCalls(Callable a, Callable b) {
    not (b.getFile().toString().matches("Test%")) and
    (
        (a.calls(b) and b.isStatic())
        or 
        (a.callsImpl(b) and not b.isStatic())
    ) and
    (
        filter1(a, b) or
        filter2(a, b) or
        filter3(a, b) or
        filter4(a, b)
    )
}



predicate filter1(Callable a, Callable b) {
    not (a.getName() = "create" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs", "DistributedFileSystem")) or
    (
        a.getName() = "create" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs", "DistributedFileSystem") and
        (
            (b.getName() = "resolve" and b.getDeclaringType().hasQualifiedName("org.apache.hadoop.fs", "FileSystemLinkResolver"))
            or not (b.getName() = "resolve")
        )
    ) 

}

// it only works when src is create() in DistributedFileSystem
predicate filter2(Callable a, Callable b) {
    not (a.getName() = "resolve" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.fs", "FileSystemLinkResolver")) or
    (
        a.getName() = "resolve" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.fs", "FileSystemLinkResolver") and
        (
            (b.getName() = "next" and b.getLocation().getFile().toString() = "DistributedFileSystem" and b.getLocation().getStartLine() = 542)
            or not (b.getName() = "next")
        )
    )
}

// it only works when src is create() in DistributedFileSystem
predicate filter3(Callable a, Callable b) {
    not (a.getName() = "resolve" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.fs", "FileSystemLinkResolver")) or
    (
        a.getName() = "resolve" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.fs", "FileSystemLinkResolver") and
        (
            (b.getName() = "doCall" and b.getLocation().getFile().toString() = "DistributedFileSystem" and b.getLocation().getStartLine() = 533)
            or not (b.getName() = "doCall")
        )
    )
}

predicate filter4(Callable a, Callable b) {
    not (a.getName() = "newStreamForCreate" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs", "DFSOutputStream")) or
    (
        a.getName() = "newStreamForCreate" and a.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs", "DFSOutputStream") and
        (
            (b.getName() = "create" and b.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.protocolPB", "ClientNamenodeProtocolTranslatorPB"))
            or not (b.getName() = "create")
        )
    )
}

// predicate validMetadataNames(string name) {
//     name = "BufferCell" or
//     name = "BTreeRow" or
//     name = "EncodingStats" or
//     name = "BTreePartitionData" or
//     name = "AtomicBTreePartition" or
//     name = "LivenessInfo" or
//     name = "BufferDecoratedKey"
// }

// class MetadataCallable extends Callable {
//     MetadataCallable() {
//         this instanceof Constructor and 
//         (
//             (
//                 this.getName() = "BufferCell" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "BufferCell")
//             )
//             or (
//                 this.getName() = "BTreeRow" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "BTreeRow")
//             ) 
//             or (
//                 this.getName() = "EncodingStats" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.rows", "EncodingStats")
//             ) 
//             or (
//                 this.getName() = "BTreePartitionData" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.partitions", "BTreePartitionData")
//             ) 
//             or (
//                 this.getName() = "AtomicBTreePartition" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db.partitions", "AtomicBTreePartition")
//             ) 
//             or (
//                 this.getName() = "LivenessInfo" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db", "LivenessInfo")
//             ) 
//             or (
//                 this.getName() = "BufferDecoratedKey" and
//                 this.getDeclaringType().hasQualifiedName("org.apache.cassandra.db", "BufferDecoratedKey")
//             )
//         )
//     }
// }

predicate ifStmtWithThrow(IfStmt ifStmt) {
    exists(
        ThrowStmt throwStmt |
        ifStmt.getElse() = throwStmt.getParent()
        or ifStmt.getThen() = throwStmt.getParent() 
        or ifStmt = throwStmt.getParent() // if (...) throw ...; else throw ...;
    )
}

predicate ifStmtWithReturn(IfStmt ifStmt) {
    exists(
        ReturnStmt returnStmt |
        ifStmt.getElse() = returnStmt.getParent() or
        ifStmt.getThen() = returnStmt.getParent()
    )
}

// predicate methodCallWithIfStmt(MethodCall call, IfStmt ifStmt, int depth) {
//     depth in [1 .. 5] and
//     (
//         (depth = 1 and ifStmt.getEnclosingCallable() = call.getCallee()) or
//         (
//             depth > 1 and
//             exists(
//                 MethodCall innerCall |
//                 call.getCallee() = innerCall.getCaller() and
//                 methodCallWithIfStmt(innerCall, ifStmt, depth - 1)
//             )
//         )   
//     )
// }

// predicate methodCallWithMetadata(MethodCall call, ClassInstanceExpr newObj, int depth) {
//     validMetadataNames(newObj.getType().getName()) and
//     depth in [1 .. 5] and
//     (
//         (depth = 1 and newObj.getEnclosingCallable() = call.getCallee()) or
//         (
//             depth > 1 and
//             exists(
//                 MethodCall innerCall |
//                 call.getCallee() = innerCall.getCaller() and
//                 methodCallWithMetadata(innerCall, newObj, depth - 1)
//             )
//         )
//     )
// }