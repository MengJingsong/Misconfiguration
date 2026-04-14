import java

class PatternIfCallable extends Callable {
    int getAPatternIfStmtStartLine() {
      isPattern2Location(this.getFile().getRelativePath(), this.getLocation().getStartLine(), result)
    }

    PatternIfCallable() {
      exists(int ifStmtLine |
        isPattern2Location(this.getFile().getRelativePath(), this.getLocation().getStartLine(), ifStmtLine
        )
      )
    }
}

predicate isPattern2Location(string path, int startLine, int ifStmtLine) {
  (
    path = "src/java/org/apache/cassandra/db/ReadCommand.java" and startLine = 676 and ifStmtLine = 679
  ) or (
    path = "src/java/org/apache/cassandra/db/filter/IndexHints.java" and startLine = 373 and ifStmtLine = 378
  ) or (
    path = "src/java/org/apache/cassandra/db/filter/IndexHints.java" and startLine = 373 and ifStmtLine = 381
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 683
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 689
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 694
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 699
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 702
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 720
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 731
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 744
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 907
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 919
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 921
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 929
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 936
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 939
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 949
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 968
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 987
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1003
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1049
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1066
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1086
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1089
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1095
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1133
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1136
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1138
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1152
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1193
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 582 and ifStmtLine = 1208
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 1293 and ifStmtLine = 1299
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 1661 and ifStmtLine = 1674
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 5490 and ifStmtLine = 5497
  ) or (
    path = "src/java/org/apache/cassandra/config/DatabaseDescriptor.java" and startLine = 5490 and ifStmtLine = 5502
  ) or (
    path = "src/java/org/apache/cassandra/config/GuardrailsOptions.java" and startLine = 1438 and ifStmtLine = 1442
  ) or (
    path = "src/java/org/apache/cassandra/config/GuardrailsOptions.java" and startLine = 1448 and ifStmtLine = 1452
  ) or (
    path = "src/java/org/apache/cassandra/cql3/QueryProcessor.java" and startLine = 874 and ifStmtLine = 881
  ) or (
    path = "src/java/org/apache/cassandra/locator/AbstractReplicationStrategy.java" and startLine = 356 and ifStmtLine = 364
  ) or (
    path = "src/java/org/apache/cassandra/cql3/statements/schema/AlterKeyspaceStatement.java" and startLine = 184 and ifStmtLine = 201
  ) or (
    path = "src/java/org/apache/cassandra/service/StorageService.java" and startLine = 1548 and ifStmtLine = 1551
  ) or (
    path = "src/java/org/apache/cassandra/dht/BootStrapper.java" and startLine = 221 and ifStmtLine = 238
  )
}