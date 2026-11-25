#!/usr/bin/env bash
# B26 LOAD lifetime (heap 8G, not a reading): schema, data, flush, count, drain, SIGTERM; then the template.
set -uo pipefail
ROOT=/mydata/s4/b26; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
$V start LOAD LOAD 8G || exit 1; $V ready LOAD || exit 1
bash $H/client.sh LOAD schema 127.0.0.1 && bash $H/client.sh LOAD load 127.0.0.1 || exit 1
$NT flush b26; bash $H/client.sh LOAD count 127.0.0.1
$V stop LOAD
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls $ROOT/template/data/b26/
echo LOAD done
