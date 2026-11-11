#!/usr/bin/env python3
"""Counts the case's log evidence in one node log directory, rotated .zip files included.
usage: logscan.py <log dir>   -> one line of key=value"""
import os, re, sys, zipfile
d = sys.argv[1]
def lines(prefix):
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if not n.startswith(prefix):
            continue
        if n.endswith('.zip'):
            with zipfile.ZipFile(p) as z:
                for m in z.namelist():
                    for l in z.read(m).decode('utf-8', 'replace').splitlines():
                        yield l
        elif n == prefix:
            for l in open(p, errors='replace'):
                yield l.rstrip('\n')
c = dict(warn_rejecting=0, error_entries=0, error_cdcwrite=0, small_cdc=0, cdc_enabled_line=0, freed_up=0, startup_complete=0)
first = last = ''
for l in lines('system.log'):
    if l.startswith('WARN') and 'Rejecting mutation' in l:
        c['warn_rejecting'] += 1
        ts = re.search(r'(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d,\d+)', l)
        if ts:
            first = first or ts.group(1); last = ts.group(1)
    if l.startswith('ERROR'):
        c['error_entries'] += 1
    if l.startswith('ERROR') and 'CDCWriteException' in l or (l.startswith('org.apache.cassandra.exceptions.CDCWriteException')):
        c['error_cdcwrite'] += 1
    if 'Small cdc volume detected' in l:
        c['small_cdc'] += 1
    if 'Starting casssandra node with Change-Data-Capture enabled' in l:
        c['cdc_enabled_line'] += 1
    if 'Startup complete' in l:
        c['startup_complete'] += 1
for l in lines('debug.log'):
    if 'Freed up' in l and 'after deleting the oldest CDC commit log segments' in l:
        c['freed_up'] += 1
print(' '.join('%s=%s' % kv for kv in c.items()) + ' first_rejecting=%s last_rejecting=%s' % (first.replace(' ', 'T'), last.replace(' ', 'T')))
