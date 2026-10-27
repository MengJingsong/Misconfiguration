#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 logs (no use of the harness's .stage4 extracts or summaries).
Usage: selfcheck.py <unit-dir> <cluster-dir>"""
import sys,re,csv,glob,os
u,c=sys.argv[1:3]
GIB=1<<30
print("== unit: raw JUnit output, WARN lines taken from the logback line itself")
for f in sorted(glob.glob(u+"/*.out")):
    t=open(f,errors="ignore").read()
    name=os.path.basename(f)[:-4]
    # real WARN log events from DatabaseDescriptor (not the test's own echo): 'WARN  [main] ... DatabaseDescriptor.java:727 - Only X free'
    warn=re.findall(r"^WARN +\[main\].*DatabaseDescriptor\.java:(\d+) - (Only \S+ free across all data volumes)",t,flags=re.M)
    ok=re.search(r"^OK \(1 test\)",t,flags=re.M) is not None
    m=re.search(r"sum_bytes=(\d+)",t); s=int(m.group(1)) if m else None
    exp= (s<64*GIB) if s is not None else None
    print("%-9s sum=%-14s sum<64GiB=%-5s real_WARN_events=%d %s test_OK=%s" % (name,s,exp,len(warn),sorted(set(w[0] for w in warn)),ok))
    if s is not None and (len(warn)>0)!=exp and name!="nodirs": print("   MISMATCH")
print("== cluster")
for a in "SLC":
    d=c+"/"+a
    log=open(d+"/logs/system.log",errors="ignore").read()
    w=re.findall(r"^WARN .*DatabaseDescriptor\.java:727 - (Only \S+ free)",log,flags=re.M)
    rows=list(csv.DictReader(open(d+"/samples.csv")))
    mx=lambda k:max(float(r[k]) for r in rows if r[k])
    alive=[r["node_alive"] for r in rows]
    cfg=re.findall(r"commitlog_total_space=([^;]*);",log)
    print(a,"WARN:",w,"| vol_used_max=%d data_max=%d commitlog_max=%d alive_first=%s alive_last=%s commitlog_total_space in logged config=%s"%(mx("vol_used"),mx("data_bytes"),mx("commitlog_bytes"),alive[0],alive[-1],cfg[:1]))
    print("   ERROR lines:",len(re.findall(r"^ERROR",log,flags=re.M)),"| 'No space left':",len(re.findall("No space left",log)),"| Stopping transports:",len(re.findall("Stopping transports",log)))
    # stress results block: read the tail only
    with open(d+"/stress.out","rb") as fh:
        fh.seek(0,2); n=fh.tell(); fh.seek(max(0,n-6000)); tail=fh.read().decode(errors="ignore")
    tp=re.findall(r"Total partitions\s*:\s*([\d,]+)",tail); te=re.findall(r"Total errors\s*:\s*([\d,]+)",tail)
    print("   stress: partitions",tp[-1:],"errors",te[-1:])
    # first time data_bytes >=3.5 GiB (elapsed from first sample with >5MB)
    t0=next(int(r["epoch_ms"]) for r in rows if float(r["data_bytes"] or 0)>5e6)
    hit=[ (int(r["epoch_ms"])-t0)/1000 for r in rows if float(r["data_bytes"] or 0)>=3.5*GIB]
    print("   seconds (from first >5MB data) to reach 3.5 GiB data:",hit[:1])
