import sys,time
b=bytearray(600*1024*1024)
for i in range(0,len(b),4096): b[i]=1
time.sleep(1800)
