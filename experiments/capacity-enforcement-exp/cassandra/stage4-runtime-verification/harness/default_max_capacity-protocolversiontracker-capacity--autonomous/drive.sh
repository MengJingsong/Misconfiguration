#!/usr/bin/env bash
# o134 detached driver: records its PID in /mydata/s4/DRIVER-jingsong-o134.pid, removes it at the end.
R=/mydata/jingsong-cass-s4/o134
echo $$ > /mydata/s4/DRIVER-jingsong-o134.pid
for ph in "$@"; do
  echo "DRIVER $ph start $(date -u +%FT%TZ)" >> $R/logs/driver.log
  case $ph in
    setup) bash $R/harness/setup.sh ;;
    unit) bash $R/harness/unit-all.sh ;;
    stock|uncapped) bash $R/harness/cluster-run.sh $ph ;;
  esac
  rc=$?; echo "DRIVER $ph exit $rc $(date -u +%FT%TZ)" >> $R/logs/driver.log
  [ $rc -eq 0 ] || break
done
echo "DRIVER END $(date -u +%FT%TZ)" >> $R/logs/driver.log
rm -f /mydata/s4/DRIVER-jingsong-o134.pid
