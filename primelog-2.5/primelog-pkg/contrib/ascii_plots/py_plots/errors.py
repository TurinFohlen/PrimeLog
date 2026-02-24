#!/usr/bin/env python3
"""
py_plots/errors.py  —  错误分布柱状图
stdin:  TSV，header = error_type\tcount
stdout: ASCII 柱状图
"""
import sys
import plotext as plt

lines = [l.rstrip('\n') for l in sys.stdin if l.strip()]
if not lines:
    sys.exit("no input")

# 跳过 header 或 ERROR 行
data_lines = [l for l in lines if '\t' in l and not l.startswith('error_type') and not l.startswith('ERROR')]
if not data_lines:
    sys.exit("no data")

names, counts = [], []
for line in data_lines:
    parts = line.split('\t')
    if len(parts) >= 2:
        names.append(parts[0])
        try:
            counts.append(int(parts[1]))
        except ValueError:
            pass

if not names:
    sys.exit("no data")

plt.clf()
plt.bar(names, counts)
plt.title("PrimeLog · Error Distribution")
plt.xlabel("Error Type")
plt.ylabel("Count")
plt.theme("clear")
plt.show()
