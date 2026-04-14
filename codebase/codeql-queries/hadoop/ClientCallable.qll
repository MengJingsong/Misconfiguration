import java

class ClientCallable extends Callable {
    ClientCallable() {
        this.getDeclaringType().hasQualifiedName("org.apache.hadoop.hdfs.server.namenode", "NameNodeRpcServer")
        and this.getName() in ["create", "append", "open", "rename", "delete", "listStatus", "setReplication", "setPermission", "setOwner"]
        
    }
}