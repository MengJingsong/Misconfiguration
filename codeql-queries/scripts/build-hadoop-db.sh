#!/usr/bin/env bash
# Build the Hadoop CodeQL database (hadoop-db) for if-check-exp stage 1.
#
# Traces a real Maven build, the way cassandra-db traced Cassandra's ant build,
# so every type resolves (including generated protobuf classes). Builds a
# local-disk copy of systems/hadoop/source: never build in the repository's copy.
#
# The whole default reactor is built (not only the four core projects): stage-1
# scope is applied by the queries (ifcheck/IfCheck.qll, inMainSource), so the
# database is reusable if the scope ever widens.
#
# Usage: build-hadoop-db.sh            (env overrides below)
#   WORK          local work dir            (default /mydata/hadoop-codeql)
#   CODEQL_DB_ROOT where hadoop-db ends up  (default /proj/misconfiguration-PG0/codeql-dbs)
#   CODEQL_BIN    codeql executable         (default: codeql on PATH)
#   JAVA8_HOME    JDK 8 (Hadoop 3.4 builds with javac 1.8)
#   MVN_THREADS   Maven -T value            (default 1C)
#   FORCE=1       replace an existing $CODEQL_DB_ROOT/hadoop-db
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="${HADOOP_SRC:-$REPO_ROOT/systems/hadoop/source}"
WORK="${WORK:-/mydata/hadoop-codeql}"
DB_ROOT="${CODEQL_DB_ROOT:-/proj/misconfiguration-PG0/codeql-dbs}"
CODEQL="${CODEQL_BIN:-codeql}"
JAVA8_HOME="${JAVA8_HOME:-/usr/lib/jvm/java-8-openjdk-amd64}"
MVN_THREADS="${MVN_THREADS:-1C}"

[ -f "$SRC/hadoop-project/pom.xml" ] || { echo "no Hadoop source at $SRC" >&2; exit 1; }
grep -q '<version>3.4.2</version>' "$SRC/hadoop-project/pom.xml" || { echo "$SRC is not Hadoop 3.4.2" >&2; exit 1; }
[ -x "$JAVA8_HOME/bin/javac" ] || { echo "no JDK 8 at $JAVA8_HOME (apt install openjdk-8-jdk-headless)" >&2; exit 1; }
command -v mvn >/dev/null || { echo "mvn not found (apt install maven)" >&2; exit 1; }
command -v "$CODEQL" >/dev/null || { echo "codeql not found; export PATH=/proj/misconfiguration-PG0/tools/codeql:\$PATH" >&2; exit 1; }
if [ -e "$DB_ROOT/hadoop-db" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "$DB_ROOT/hadoop-db exists; set FORCE=1 to replace it" >&2; exit 1
fi

mkdir -p "$WORK"
echo "== copying source to $WORK/src"
rsync -a --delete "$SRC/" "$WORK/src/"

# Build-tooling fix, applied to the local copy only (never the repository's): the
# release pins Node v12.22.1 for hadoop-yarn-applications-catalog-webapp's frontend
# build, but its yarn dependencies now require Node >= 18 (`color@5.0.3`), so the
# default build fails there. Same versions as systems/hadoop/build-src/
# step2-CorrectHadoopPOM.sh. Touches no Java source, so the analysed code is unchanged.
POM="$WORK/src/hadoop-project/pom.xml"
sed -E -i 's|<nodejs.version>[^<]*</nodejs.version>|<nodejs.version>v20.12.2</nodejs.version>|; s|<yarnpkg.version>[^<]*</yarnpkg.version>|<yarnpkg.version>v1.22.22</yarnpkg.version>|' "$POM"
grep -q '<nodejs.version>v20.12.2</nodejs.version>' "$POM" && grep -q '<yarnpkg.version>v1.22.22</yarnpkg.version>' "$POM" \
  || { echo "could not apply the Node/Yarn version fix to $POM" >&2; exit 1; }

export JAVA_HOME="$JAVA8_HOME"
export PATH="$JAVA_HOME/bin:$PATH"
MVN_CMD="mvn -B -e -T $MVN_THREADS -DskipTests -DskipShade -Dmaven.javadoc.skip=true clean install"
echo "== codeql database create (build: $MVN_CMD)"
"$CODEQL" database create "$WORK/hadoop-db" --overwrite --language=java \
  --source-root "$WORK/src" --threads=0 --command="$MVN_CMD"

echo "== copying database to $DB_ROOT/hadoop-db"
rm -rf "$DB_ROOT/hadoop-db.tmp"
rsync -a "$WORK/hadoop-db/" "$DB_ROOT/hadoop-db.tmp/"
rm -rf "$DB_ROOT/hadoop-db"
mv "$DB_ROOT/hadoop-db.tmp" "$DB_ROOT/hadoop-db"
echo "== done: $DB_ROOT/hadoop-db"
