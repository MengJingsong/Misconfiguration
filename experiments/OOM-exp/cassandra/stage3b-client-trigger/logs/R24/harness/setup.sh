#!/usr/bin/env bash
# 3-b R24 setup on pc72 (2026-11-24): copy of the built 5.0.9 tree (read only source /mydata/s4/cassandra-base), the shipped conf
# (conf-pristine) and conf-auth = shipped conf with exactly two lines changed (authenticator, authorizer); compile clients.
set -euo pipefail
ROOT=/mydata/s4/3b-R24
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
rm -rf "$ROOT/conf-auth"; cp -a "$ROOT/conf-pristine" "$ROOT/conf-auth"
sed -i -e 's/^authenticator: AllowAllAuthenticator$/authenticator: PasswordAuthenticator/' -e 's/^authorizer: AllowAllAuthorizer$/authorizer: CassandraAuthorizer/' "$ROOT/conf-auth/cassandra.yaml"
diff "$ROOT/conf-pristine/cassandra.yaml" "$ROOT/conf-auth/cassandra.yaml" > "$ROOT/conf-auth.diff" || true
cat "$ROOT/conf-auth.diff"; md5sum "$ROOT/conf-pristine/cassandra.yaml" "$ROOT/conf-auth/cassandra.yaml"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/R24Load.java" "$ROOT/harness/R24Sampler.java" "$ROOT/harness/RfpJmx.java" "$ROOT/harness/R24Victim.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
