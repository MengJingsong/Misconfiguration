#!/usr/bin/env bash
# Frozen hashes of the amended case file: whole file and each predictions/conclusions block (header line included,
# up to but not including the next block's header line). Run in ~/writeup-hadoop/out/o31.
set -euo pipefail
f=${1:-case-amended.md}
sha256sum "$f"
for r in "B2f:/^\*\*B2f\./,/^\*\*B2g\./" "B2g:/^\*\*B2g\./,/^\*\*B2h\./" "B3f:/^\*\*B3f\./,/^\*\*B3g\./" "B3g:/^\*\*B3g\./,/^\*\*B3h\./"; do
  n=${r%%:*}; rg=${r#*:}
  echo "$n $(sed -n "${rg}p" "$f" | sed '$d' | sha256sum | cut -c1-64)"
done
