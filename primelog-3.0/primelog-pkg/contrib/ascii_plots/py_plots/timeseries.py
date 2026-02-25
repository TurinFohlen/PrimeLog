#!/usr/bin/env python3
"""
py_plots/timeseries.py  —  错误随时间变化折线图
stdin:  TSV，header = t\terror_count\tnone_count
stdout: ASCII 折线图
"""
import sys
import plotext as plt

lines = [l.rstrip('\n') for l in sys.stdin if l.strip()]
data_lines = [l for l in lines
              if '\t' in l
              and not l.startswith('t\t')
              and not l.startswith('ERROR')]

if not data_lines:
    sys.exit("no data")

ts, errs, nones = [], [], []
for line in data_lines:
    parts = line.split('\t')
    if len(parts) >= 3:
        try:
            ts.append(float(parts[0]))
            errs.append(int(parts[1]))
            nones.append(int(parts[2]))
        except ValueError:
            pass

if not ts:
    sys.exit("no data")

plt.clf()
plt.plot(ts, errs,  label="errors",  color="red")
plt.plot(ts, nones, label="success", color="green")
plt.title("PrimeLog · Events Over Time")
plt.xlabel("Time (s)")
plt.ylabel("Count")
plt.theme("clear")
plt.show()
