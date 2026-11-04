#!/usr/bin/env python3
"""Compressible-value loader (B2i.5): n rows of a repeated-byte blob. Usage: loader.py <driver-zip> <n> <valuebytes>"""
import sys, threading
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
n = int(sys.argv[2]); vb = int(sys.argv[3])
c = Cluster(['127.0.0.1'], protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect()
s.execute("CREATE KEYSPACE IF NOT EXISTS segks WITH replication={'class':'SimpleStrategy','replication_factor':1}")
s.execute("CREATE TABLE IF NOT EXISTS segks.t (k bigint PRIMARY KEY, v blob)")
ps = s.prepare("INSERT INTO segks.t (k,v) VALUES (?,?)")
v = bytes([7]) * vb
sem = threading.Semaphore(128); err = [0]
def ok(_): sem.release()
def bad(e): err[0] += 1; sem.release()
for i in range(n):
    sem.acquire()
    f = s.execute_async(ps, (i, v)); f.add_callbacks(ok, bad)
for _ in range(128): sem.acquire()
print('LOADER_DONE rows', n, 'errors', err[0])
c.shutdown()
