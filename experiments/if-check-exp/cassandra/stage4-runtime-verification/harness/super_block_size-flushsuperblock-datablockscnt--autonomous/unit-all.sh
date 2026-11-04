#!/usr/bin/env bash
# usage: unit-all.sh   (the whole unit tier B2e as amended 2026-10-28). Overlays must exist (make-overlays.sh).
set -uo pipefail
HARN=$(cd "$(dirname "$0")" && pwd); R="$HARN/unit-run.sh"; X=512m
echo "== unit tier start $(date -u +%FT%TZ)"
# 1-3: constants x N (sweep), 3 repeats at 200000
for c in 16 64 256; do
  for n in 50000 400000; do $R sp$c-n$n ov${c}p $n SPARSE $X; done
  for rep in 1 2 3; do $R sp$c-n200000-r$rep ov${c}p 200000 SPARSE $X; done
done
$R sp64-n2000 ov64p 2000 SPARSE $X                      # fewer than 64 blocks: only the forced final flush
$R pfx64-n200000 ov64p 200000 PREFIX $X                 # structural control: no super blocks
$R ov64-unpatched-n200000 ov64 200000 SPARSE $X         # unpatched overlay: md5 equals the patched one
$R pristine-n200000 pristine 200000 SPARSE $X           # the build's own class (constant 64, no overlay)
$R sp64-n200000-xmx2g ov64p 200000 SPARSE 2g            # informational: B2e(5)
$R sp64-n200000-xmx64m ov64p 200000 SPARSE 64m          # informational: B2e(5), may fail with OutOfMemoryError
echo "== unit tier end $(date -u +%FT%TZ)"
