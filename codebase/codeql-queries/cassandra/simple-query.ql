import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
import ConfigSig

from
    IfStmt ifStmt, ThrowStmt throwStmt
where
    ifStmt.getFile().getBaseName() = "DatabaseDescriptor.java"
    and ifStmt.getLocation().getStartLine() = 1170
    and throwStmt.getFile().getBaseName() = "DatabaseDescriptor.java"
    and throwStmt.getLocation().getStartLine() = 1171
    and ifStmt.getThen() = throwStmt
select
    ifStmt, throwStmt, throwStmt.getParent(), ifStmt.getThen()


// from
//     FieldDeclaration fd, Field f, Method method, MethodCall mc
// where
//     fd.getFile().getBaseName() = "Config.java"
//     and fd.getAField() = f
//     and f.getType() instanceof RefType
//     and not f.getType().getName() = "Integer"
//     and not f.getType().getName() = "Double"
//     and not f.getType().getName() = "Float"
//     and not f.getType().getName() = "String"
//     and not f.getType().getName() = "Boolean"
//     and not f.getType() instanceof Interface
//     and f.getType().(RefType).getAMethod() = method
//     and method.getName().matches("to%")
//     and not method.getName() = "toString"
//     and mc.getCallee() = method
// select
//     fd, f, f.getLocation().getStartLine() as line,
//     f.getType() as type,
//     method, mc

// from
//     DataFlow::Node source
// where
//     refTypeSource(source)
//     and source.asExpr() instanceof MethodCall
//     and source.asExpr().(MethodCall).getQualifier() instanceof FieldAccess
// select
//     source, source.asExpr().(MethodCall).getQualifier() as qualifier,
//     qualifier.(FieldAccess).getField() as field

// from
//     FieldAccess fa
// where
//     fa.getLocation().getStartLine() = 3455
//     and fa.getField().getName() = "internode_socket_send_buffer_size"
//     and fa.getField().getDeclaringType().hasQualifiedName("org.apache.cassandra.config", "Config")
//     and fa.getField().isPublic() and not fa.getField().isFinal()
// select
//     fa, 
//     fa.getField() as field,
//     fa.(VarAccess).getType() as type,
//     fa.getVariable() as var,
//     var.getType().(RefType).getSourceDeclaration() as decl,
//     decl.getAMethod() as declMethod

// from
//     ReturnStmt stmt 
// where
//     stmt.getLocation().getFile().getBaseName() = "DatabaseDescriptor.java"
//     and stmt.getLocation().getStartLine() = 3460
// select
//     stmt,
//     stmt.getResult() as res,
//     res.