#!/usr/bin/env python3
# Parse `jcmd <pid> VM.native_memory summary` on stdin -> one CSV line: epoch_ms,Other committed KB,Internal committed KB,Total committed KB
import sys, re
t = sys.argv[1]; txt = sys.stdin.read()
def com(label):
    m = re.search(r'-\s+' + label + r' \(reserved=\d+KB, committed=(\d+)KB\)', txt)
    return m.group(1) if m else ''
m = re.search(r'Total: reserved=\d+KB, committed=(\d+)KB', txt)
if m: print(f"{t},{com('Other')},{com('Internal')},{m.group(1)}")
