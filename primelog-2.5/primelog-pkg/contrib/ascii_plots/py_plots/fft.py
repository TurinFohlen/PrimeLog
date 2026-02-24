#!/usr/bin/env python3
"""
py_plots/fft.py  —  错误信号 FFT 频谱
stdin:  TSV，header = freq_hz\tamplitude
stdout: ASCII 折线图
"""
import sys
import plotext as plt

lines = [l.rstrip('\n') for l in sys.stdin if l.strip()]
data_lines = [l for l in lines
              if '\t' in l
              and not l.startswith('freq_hz')
              and not l.startswith('ERROR')]

if not data_lines:
    sys.exit("no data")

freqs, amps = [], []
for line in data_lines:
    parts = line.split('\t')
    if len(parts) >= 2:
        try:
            freqs.append(float(parts[0]))
            amps.append(float(parts[1]))
        except ValueError:
            pass

if not freqs:
    sys.exit("no data")

plt.clf()
plt.plot(freqs, amps, color="cyan")
plt.title("PrimeLog · Error Signal FFT Spectrum")
plt.xlabel("Frequency (Hz)")
plt.ylabel("Normalised Amplitude")
plt.ylim(0, 1.05)
plt.theme("clear")
plt.show()
