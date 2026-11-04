#!/usr/bin/env python3
"""Shared node helpers for the SAI hard-coded-constant cases (batch 3/4, 2026-10-28). Copied unchanged into each case's harness folder.
One node from a run copy (cassandra tree built with ant): its own conf/ and every directory under a per-run root on local disk, a loopback address
(127.0.0.N) and a JMX port of its own so that two runs on one host do not collide, G1 with only MAX_HEAP_SIZE set, GC log, optional Byteman agent.
Everything is logged to <out>/cmdlog.txt; the node is stopped on any exit."""
import atexit, os, re, subprocess, threading, time

HOME = os.path.expanduser('~')

class Node:
    def __init__(self, copy, root, out, label, heap='4G', yaml_lines='', jvm_extra='', byteman_script=None, jmx_port=7199, ip='127.0.0.1', extra_env=None):
        self.C, self.T, self.out, self.label = copy, root, out, label
        self.heap, self.yaml_lines, self.jvm_extra, self.byteman = heap, yaml_lines, jvm_extra, byteman_script
        self.jmx, self.ip = jmx_port, ip
        os.makedirs(out, exist_ok=True)
        self.log = open(out + '/cmdlog.txt', 'a')
        self.stopflag = threading.Event(); self.proc = None; self.extra_env = extra_env or {}; self.pid = None
        atexit.register(self.stop)

    def say(self, *a):
        m = ' '.join(str(x) for x in a); print(m, flush=True); self.log.write(m + '\n'); self.log.flush()

    def sh(self, cmd, tmo=3600, show=1500, check=False, cwd=None, env=None):
        self.say('$', cmd)
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=cwd or self.C, timeout=tmo, env=env)
        self.say(r.stdout.rstrip()[-show:])
        if check and r.returncode != 0: raise RuntimeError('command failed rc=%d: %s' % (r.returncode, cmd))
        return r.stdout

    def daemons(self):
        out = subprocess.run("ps -eo pid,comm,args | awk '$2==\"java\" && /CassandraDaemon/'", shell=True, capture_output=True, text=True).stdout
        return [l for l in out.splitlines() if l.strip() and (self.T + '/conf') in l]

    def make_conf(self, wipe_data=True):
        T = self.T
        if wipe_data: subprocess.run('rm -rf %s' % T, shell=True)
        for d in ('logs', 'data', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'): os.makedirs('%s/%s' % (T, d), exist_ok=True)
        subprocess.run('rm -rf %s/conf; cp -r %s/conf %s/conf' % (T, self.C, T), shell=True, check=True)
        subprocess.run("sed -i 's/^JMX_PORT=\"7199\"/JMX_PORT=\"%d\"/' %s/conf/cassandra-env.sh" % (self.jmx, T), shell=True, check=True)
        shipped = open(self.C + '/conf/cassandra.yaml').read()
        add = ('cluster_name: stage4-sai\nnum_tokens: 1\nendpoint_snitch: SimpleSnitch\nlisten_address: %s\nrpc_address: %s\n' % (self.ip, self.ip)
               + 'seed_provider:\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: "%s:7000"\n' % self.ip
               + 'data_file_directories:\n    - %s/data\ncommitlog_directory: %s/commitlog\nhints_directory: %s/hints\nsaved_caches_directory: %s/saved_caches\ncdc_raw_directory: %s/cdc_raw\n' % (T, T, T, T, T)
               + self.yaml_lines).splitlines()
        keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
        outl, skip = [], False
        for l in shipped.splitlines():
            m = re.match(r'^([A-Za-z_]+):', l)
            if m:
                skip = m.group(1) in keys
                if skip: continue
            elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')): continue
            else: skip = False
            outl.append(l)
        open(T + '/conf/cassandra.yaml', 'w').write('\n'.join(outl) + '\n# ---- stage4 lines ----\n' + '\n'.join(add) + '\n')
        self.say('conf written %s/conf/cassandra.yaml; stage4 lines:\n' % T + '\n'.join(add))

    def start(self, timeout=300):
        assert not self.daemons(), 'a CassandraDaemon of this run root is already running'
        extra = self.jvm_extra + ' -Xlog:gc*:file=%s/gc-%s.log:time,uptime:filecount=0' % (self.out, self.label)
        if self.byteman:
            extra += ' -javaagent:%s/build/lib/jars/byteman-4.0.20.jar=script:%s' % (self.C, self.byteman)
        open(self.out + '/jvm-extra.txt', 'w').write(extra + '\n')
        env = dict(os.environ, CASSANDRA_CONF=self.T + '/conf', CASSANDRA_LOG_DIR=self.T + '/logs', MAX_HEAP_SIZE=self.heap, JVM_EXTRA_OPTS=extra, **self.extra_env)
        self.t_launch = int(time.time() * 1000)
        self.proc = subprocess.Popen('ulimit -n 100000; exec bin/cassandra -f > %s/stdout.txt 2>&1' % self.T, shell=True, cwd=self.C, env=env, start_new_session=True)
        for _ in range(timeout // 3):
            r = subprocess.run('bin/nodetool -p %d statusbinary' % self.jmx, shell=True, cwd=self.C, capture_output=True, text=True)
            if r.stdout.strip() == 'running': break
            if self.proc.poll() is not None:
                self.say('daemon died at start'); self.say(open(self.T + '/stdout.txt').read()[-3000:]); raise RuntimeError('daemon died')
            time.sleep(3)
        else: raise RuntimeError('node did not come up')
        ds = self.daemons(); self.pid = int(ds[0].split()[0])
        self.say('NODE_UP pid=%d startup_s=%.1f' % (self.pid, (time.time() * 1000 - self.t_launch) / 1000))

    def stop(self):
        self.stopflag.set()
        if self.daemons():
            subprocess.run('bin/nodetool -p %d stopdaemon' % self.jmx, shell=True, cwd=self.C, capture_output=True)
            for _ in range(60):
                if not self.daemons(): break
                time.sleep(2)
            for l in self.daemons(): os.kill(int(l.split()[0]), 9)
        self.say('daemons left (this run root): %d' % len(self.daemons()))

    def sampler(self, name='heap.csv', period=2.0):
        """jcmd GC.heap_info every <period> s -> heap_used_kB (G1 'used' of the heap line) and VmRSS."""
        self.sflag = threading.Event()
        f = open('%s/%s' % (self.out, name), 'w'); f.write('epoch_ms,heap_used_kB,rss_kB\n')
        def run():
            while not self.stopflag.is_set() and not self.sflag.is_set():
                try:
                    hi = subprocess.run('jcmd %d GC.heap_info 2>/dev/null' % self.pid, shell=True, capture_output=True, text=True, timeout=30).stdout
                    m = re.search(r'used (\d+)K', hi)
                    st = dict(l.split(':', 1) for l in open('/proc/%d/status' % self.pid).read().splitlines() if ':' in l)
                    f.write('%d,%s,%s\n' % (time.time() * 1000, m.group(1) if m else -1, st['VmRSS'].split()[0])); f.flush()
                except Exception: pass
                time.sleep(period)
            f.close()
        self.sthread = threading.Thread(target=run, daemon=True); self.sthread.start()

    def sampler_stop(self):
        self.sflag.set(); self.sthread.join(timeout=40)

    def nt(self, args, tmo=7200, show=800):
        return self.sh('bin/nodetool -p %d %s' % (self.jmx, args), tmo=tmo, show=show)

    def cql(self, stmt, tmo=900, show=1500):
        return self.sh("bin/cqlsh %s -e '%s'" % (self.ip, stmt.replace("'", "'\\''")), tmo=tmo, show=show)

    def stress(self, args, tmo=14400, show=1200):
        return self.sh('tools/bin/cassandra-stress %s -node %s -port native=9042 jmx=%d' % (args, self.ip, self.jmx), tmo=tmo, show=show)
