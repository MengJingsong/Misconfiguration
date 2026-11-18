#!/usr/bin/env bash
# U4 template check (not a reading; added 2026-11-17 after 178 write timeouts during LOAD): one lifetime on a clone of
# the template (heap 8G), one first-page read (fetch 5,000) per partition 0..15; every partition must return 5,000 rows.
ROOT=/mydata/s4/u4-w1; H=$ROOT/harness; V="bash $H/victim-ctl.sh"
$V start VERIFY A 8G auto && $V ready VERIFY || exit 1
for pk in $(seq 0 15); do bash $H/load.sh VERIFY one 127.0.0.1 $pk 5000 | grep '^one'; done
$V stop VERIFY
