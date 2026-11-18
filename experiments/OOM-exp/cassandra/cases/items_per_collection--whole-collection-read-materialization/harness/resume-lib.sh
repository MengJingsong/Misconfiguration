# Resume (2026-11-18, after the API-limit interruption): lib.sh plus one change to stop_node (deviation D7):
# if a HeapDumpOnOutOfMemoryError dump is still being written when the window ends, wait for "Heap dump file created"
# (<= 900 s) before stopdaemon/kill, so the dump is not truncated. The endpoint (first OutOfMemoryError) is not affected.
source /mydata/s4/u3-w1/harness/lib.sh
eval "orig_$(declare -f stop_node)"
stop_node() {
  if [ -n "${L:-}" ] && grep -q '^Dumping heap to' "$L/node.out" 2>/dev/null; then
    local i=0
    while ! grep -q 'Heap dump file created' "$L/node.out" && [ $i -lt 900 ]; do
      kill -0 "${DPID:-0}" 2>/dev/null || break; sleep 2; i=$((i+2)); done
    log "dump wait ${i}s: $(grep -m1 'Heap dump file created' "$L/node.out")"
  fi
  orig_stop_node
}
