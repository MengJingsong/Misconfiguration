#!/usr/bin/env bash
# Pulls the small raw files of cluster-tier values from the measured node into run1/cluster/<label>/ (run from the workstation):
#   ./pull-cluster.sh b144 b272 ...                              pass 2 (the official cluster tier): node folder cluster/, repo folder cluster/
#   SRC=cluster-pass1 DEST=cluster-pass1 ./pull-cluster.sh ...   pass 1 (superseded, kept as evidence): see results §3 defect 4
# The full logs (system.log, debug.log, the stress outputs, stdout) stay on the node under ~/stage4-logs/cdc/<SRC>/<label>/.
# system.log is stored as system.log.gz holding only the lines the checks count (WARN and ERROR entries and the
# CDCWriteException stack headers); a blocking value's whole system.log is about 9 MB, one ERROR and a stack per rejected write.
set -eu
NODE=${NODE:-jason92@pc80.cloudlab.umass.edu}
SRC=${SRC:-cluster}; DEST=${DEST:-cluster}
R=$NODE:stage4-logs/cdc/$SRC
here=$(cd "$(dirname "$0")" && pwd)
for l in "$@"; do
  d=$here/$DEST/$l; mkdir -p "$d"
  for f in summary.txt readings.csv phases.csv sampler.csv sampler.events sampler.summary cdc-verdict.txt analysis.txt settings.txt \
           cassandra.yaml.diff submit-l.txt schema.txt settle-probe.txt release-probe.txt consumer-release.txt consumer.txt \
           debug-freed-up-excerpt.txt session.log; do
    scp -q -o BatchMode=yes "$R/$l/$f" "$d/" 2> /dev/null || true
  done
  # the stress outputs print every rejected write's error (2.4 MB for one B): keep the settings header, the per-interval lines' head and the Results block
  for f in stress-cdc-B.txt stress-plain-B.txt stress-cdc-C.txt; do
    ssh -o BatchMode=yes -n "$NODE" "test -f ~/stage4-logs/cdc/$SRC/$l/$f && { head -45 ~/stage4-logs/cdc/$SRC/$l/$f; echo '[... excerpt: the full output is on the node ...]'; tail -32 ~/stage4-logs/cdc/$SRC/$l/$f; }" > "$d/$f" 2> /dev/null || true
    [ -s "$d/$f" ] || rm -f "$d/$f"
  done
  ssh -o BatchMode=yes -n "$NODE" "tail -40 ~/stage4-logs/cdc/$SRC/$l/stress-cdc-A.txt" > "$d/stress-cdc-A-tail.txt" 2> /dev/null || true
  ssh -o BatchMode=yes -n "$NODE" "grep -E '^(WARN|ERROR|org.apache.cassandra.exceptions.CDCWriteException)' ~/stage4-logs/cdc/$SRC/$l/system.log | gzip -c" > "$d/system.log.gz"
  ssh -o BatchMode=yes -n "$NODE" "wc -c < ~/stage4-logs/cdc/$SRC/$l/system.log" > "$d/system.log.size-bytes"
  echo "pulled $l: $(du -sh "$d" | cut -f1)"
done
