#!/usr/bin/env bash
# R23 S0.1-2: copy the base build, conf check, compile the load client, slow volume, data symlink.
set -euo pipefail
W=/mydata/s4/r23; C=$W/cassandra; H=$W/harness; REPO_CONF_SUMS=$H/repo-conf.sha256
mkdir -p $W/{archive,img,runs,dumps-keep}
[ -d $C ] || cp -a /mydata/s4/cassandra-base $C
rm -rf $C/logs $C/data
mkdir -p $C/data/{commitlog,hints,saved_caches}
echo "jar: $(sha256sum $C/build/apache-cassandra-*.jar)"
( cd $C/conf && sha256sum $(awk '{print $2}' $REPO_CONF_SUMS) ) | diff - $REPO_CONF_SUMS && echo "conf: identical to repo (hotspot_compiler excluded)"
$H/load.sh --compile && echo "load client compiled"
$H/slowdisk.sh setup
mkdir -p $W/vol/data
ln -sfn $W/vol/data $C/data/data
ls -la $C/data
