import java

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