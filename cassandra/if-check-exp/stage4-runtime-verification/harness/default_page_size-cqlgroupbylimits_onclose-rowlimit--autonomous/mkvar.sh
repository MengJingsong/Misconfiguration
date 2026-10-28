#!/usr/bin/env bash
# usage: mkvar.sh <name> <value>
set -e
S=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh
D=$HOME/s4-dps-$1
bash $S $D
sed -i "s/DEFAULT_PAGE_SIZE = 10000;/DEFAULT_PAGE_SIZE = $2;/" $D/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
grep -n "int DEFAULT_PAGE_SIZE" $D/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
cd $D && ant jar < /dev/null > $HOME/s4-dps-$1.build.log 2>&1; tail -3 $HOME/s4-dps-$1.build.log
