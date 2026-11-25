#!/usr/bin/env python3
"""B3a yaml edits (as amended by S4-A1) for case o127. Usage: mkconf.py <tree> <run-dir>. Idempotent: restores the pristine yaml first."""
import os, re, shutil, sys
tree, run = sys.argv[1], sys.argv[2]
y = os.path.join(tree, 'conf', 'cassandra.yaml'); orig = y + '.orig'
if not os.path.exists(orig): shutil.copy(y, orig)
s = open(orig).read()
def sub(pat, rep):
    global s
    s, n = re.subn(pat, rep, s, count=1, flags=re.M)
    assert n == 1, pat
sub(r'^num_tokens: .*$', 'num_tokens: 256')
sub(r'^allocate_tokens_for_local_replication_factor: .*$', '# allocate_tokens_for_local_replication_factor: 3   # o127: commented out (B3a)')
sub(r'^listen_address: .*$', 'listen_address: 127.0.0.1')
sub(r'^rpc_address: .*$', 'rpc_address: 127.0.0.1')
s += f"""
# ---- o127 stage-4 settings (B3a) ----
data_file_directories:
    - {run}/data
commitlog_directory: {run}/commitlog
hints_directory: {run}/hints
saved_caches_directory: {run}/saved_caches
cdc_raw_directory: {run}/cdc_raw
repair_state_size: 10
"""
open(y, 'w').write(s)
print('wrote', y)
