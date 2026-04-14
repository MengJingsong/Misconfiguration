import java

class ClientCallable extends Callable {
    ClientCallable() {
        this.getDeclaringType().hasQualifiedName("org.apache.cassandra.cql3", "QueryProcessor")
        and this.getName() in ["Process", "processStatement"]
        
    }
}