codeql commands:

  generate codeql database: codeql database create simple-java-codeql-db --language=java --command="mvn clean package"
  
  create codeql pack: codeql pack init dir
  
  add dependencies: codeql pack add codeql/java-all
