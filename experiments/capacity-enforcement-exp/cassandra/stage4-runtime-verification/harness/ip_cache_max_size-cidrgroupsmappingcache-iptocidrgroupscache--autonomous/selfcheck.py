#!/usr/bin/env python3
"""Self-check of run 1: re-reads the raw files with its own parsing (not the analyzers').
Usage: selfcheck.py <run-dir>   (holds unit/ and cluster-K*/)"""
import glob, os, re, sys
run = sys.argv[1]
print('== unit tier (raw ant logs, fragments paired key -> next fragment)')
for M in (0, 100, 100000, 1000000):
    p = f'{run}/unit/unit-{M}.log'
    fr = [l.split(' - ', 1)[1].strip() for l in open(p, errors='replace') if 'SubstituteLogger.java:222 - ' in l]
    i = fr.index('PROBE max=')
    kv = {fr[j].strip().rstrip('='): fr[j + 1] for j in range(i, i + 10, 2)}
    pol = [f for f in fr if f.startswith('PROBE policyMaximum=')]
    out = [f for f in fr if f.startswith('PROBE outsideGroups')]
    tests = [l.strip() for l in open(p) if 'Tests run:' in l]
    print(f'max={M}: {pol} {out} {kv} | {tests[-1] if tests else "no Tests run line"}')
print('== cluster tier (histograms re-read by column split)')
def rowcount(path, name):
    for l in open(path):
        parts = l.split()
        if len(parts) >= 4 and parts[3] == name: return int(parts[1]), int(parts[2])
    return 0, 0
def total(path):
    for l in open(path):
        if l.startswith('Total'): return int(l.split()[2])
for kd in sorted(glob.glob(f'{run}/cluster-K*')):
    K = kd.rsplit('K', 1)[1]
    b = rowcount(f'{kd}/h-{K}-base2.txt', 'java.net.Inet4Address')[0]
    b1 = rowcount(f'{kd}/h-{K}-base1.txt', 'java.net.Inet4Address')[0]
    d = {ph: rowcount(f'{kd}/h-{K}-{ph}.txt', 'java.net.Inet4Address')[0] - b for ph in ('w1', 'w1b', 'flushed', 'w2')}
    tb = total(f'{kd}/h-{K}-base2.txt')
    tw = total(f'{kd}/h-{K}-w1.txt')
    psms = rowcount(f'{kd}/h-{K}-w1.txt', 'com.github.benmanes.caffeine.cache.PSMS')[0] - rowcount(f'{kd}/h-{K}-base2.txt', 'com.github.benmanes.caffeine.cache.PSMS')[0]
    s = open(f'{kd}/session.txt').read()
    syslog = f'{kd}/node-logs/system.log'
    errs = sum(1 for l in open(syslog) if l.startswith('ERROR'))
    oom = [l[:80] for l in open(syslog) if 'OutOfMemoryError' in l and 'JVM Arguments' not in l]
    warn_cidr = sum(1 for l in open(syslog) if l.startswith('WARN') and 'cidr' in l.lower())
    print(f'K={K}: base1->base2 noise {b - b1}; dInet4Address w1 {d["w1"]} w1b {d["w1b"]} flushed {d["flushed"]} w2 {d["w2"]}; dPSMS w1 {psms}; '
          f'Total bytes w1-base2 {tw - tb} ({(tw - tb) / 2**20:.2f} MB)')
    y1 = 'ip_cache_max_size: "%s"' % K in s; y2 = 'cidr_groups_cache_refresh_interval: "1440"' in s; y3 = 'cidr_authorizer_mode: "MONITOR"' in s
    print(f'  yaml in session log: ip_cache_max_size={K}: {y1}; refresh 1440: {y2}; MONITOR: {y3}')
    lo = bool(re.search(r"CIDR Groups: \s*\n\s*lo", s)); w1 = open(kd + "/w1.txt").read().strip(); w2 = open(kd + "/w2.txt").read().strip()
    print(f'  getcidrgroupsofip lo: {lo}; W1: {w1}; W2: {w2}')
    print(f'  system.log: ERROR lines {errs}; OutOfMemoryError outside JVM args: {oom}; WARN with cidr: {warn_cidr}; node stopped: {"cluster K=%s done" % K in s}')
