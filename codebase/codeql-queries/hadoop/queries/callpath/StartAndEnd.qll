import java

class StartCallable extends Callable {
    StartCallable() {
        // this.getName() = "callBlockingMethod" and
        // this.getFile().toString() = "ClientNamenodeProtocolProtos"

        // (
        //     this.getName() = "create" or
        //     this.getName() = "append" or
        //     this.getName() = "rename" or
        //     this.getName() = "complete" or
        // ) and
        this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.protocolPB", "ClientNamenodeProtocolServerSideTranslatorPB")
        // this.getName() = "addFileForEditLog" and
        // this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "FSDirWriteFileOp")
    }
}

class TargetCallable extends Callable {
    TargetCallable() {
        (
            this instanceof Constructor and
            (
                (
                    this.getName() = "INodeDirectory" and
                    this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "INodeDirectory")
                )  
                or (
                    this.getName() = "INodeFile" and
                    this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "INodeFile")
                ) 
                or (
                    this.getName() = "INodeSymlink" and
                    this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "INodeSymlink")
                ) 
                or (
                    this.getName() = "INodeReference" and
                    this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "INodeReference")
                )
                or (
                    this.getName() = "BlockInfoContiguous" and
                    this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.blockmanagement", "BlockInfoContiguous")
                )
            )
        )  
        or (
            this.getName() = "put" and
            this.getDeclaringType().hasQualifiedName("org.apache.hadoop.util", "LightWeightGSet")
        )
        
        
    }
}