#!/usr/bin/env bash
set -u
WORK=${WORK:?}; tag=$1; shift
CP="$WORK/src/build/classes/main:$WORK/src/build/lib/jars/*:$WORK/src/conf"
JOPTS="$(grep -v '^#' $WORK/src/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ') -Dlogback.configurationFile=$WORK/src/conf/logback-tools.xml"
OUT=$WORK/out/$tag; rm -rf "$OUT"; mkdir -p "$OUT"
# probe args: mode limit rows valueBytes ; outDir is inserted here ; then sampleEvery stmt [partitioner]
timeout 1800 java $JOPTS ${HEAPOPTS:-} -cp "$WORK/probe/classes:$CP" MaxSizeProbe "$1" "$2" "$3" "$4" "$OUT" "${@:5}" \
    > "$WORK/logs/$tag.log" 2>&1
echo "exit=$?" | tee -a "$WORK/logs/$tag.log"
grep -E '^(WRITER|SUMMARY)' "$WORK/logs/$tag.log"
grep -m1 -E 'OutOfMemoryError' "$WORK/logs/$tag.log"
echo "data_files=$(ls $OUT/probe/t/*-Data.db 2>/dev/null | wc -l)"
echo "data_sizes=$(stat -c '%s' $OUT/probe/t/*-Data.db 2>/dev/null | sort -n | tr '\n' ' ')"
echo "data_by_id=$(for f in $(ls $OUT/probe/t/*-Data.db 2>/dev/null | sort -V); do echo -n "$(basename $f | cut -d- -f2):$(stat -c %s $f) "; done)"   # S4-A1: files in generation order
echo "du_bytes=$(du -sb $OUT/probe/t 2>/dev/null | cut -f1)"
[ "${KEEP:-0}" = 1 ] || rm -rf "$OUT"
