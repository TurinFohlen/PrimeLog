#!/usr/bin/env python3
"""
py_plots/heatmap.py  —  组件间错误热力图（ASCII 字符密度）
stdin:  NODES\tnode1\tnode2\t...
        row_name\tv00\tv01\t...
stdout: ASCII 热力图
"""
import sys

# 字符密度梯度，从冷到热
CHARS = " ·:+*#@"

def val_to_char(v, max_v):
    if max_v == 0:
        return CHARS[0]
    idx = int(v / max_v * (len(CHARS) - 1))
    return CHARS[min(idx, len(CHARS) - 1)]

lines = [l.rstrip('\n') for l in sys.stdin if l.strip()]
if not lines:
    sys.exit("no input")

nodes = []
rows  = []
row_labels = []

for line in lines:
    parts = line.split('\t')
    if parts[0] == 'NODES':
        nodes = parts[1:]
    elif parts[0] == 'ERROR':
        sys.exit("wl error: " + line)
    else:
        row_labels.append(parts[0])
        try:
            rows.append([float(v) for v in parts[1:]])
        except ValueError:
            pass

if not nodes or not rows:
    sys.exit("no data")

# 只保留 demo.* 组件（过滤掉测试残留的其他项目组件）
keep_idx = [i for i, n in enumerate(nodes) if '.' in n]
if keep_idx:
    nodes     = [nodes[i]     for i in keep_idx]
    row_labels= [row_labels[i] for i in keep_idx if i < len(row_labels)]
    rows      = [[r[i] for i in keep_idx if i < len(r)]
                 for r in rows
                 if row_labels.index(row_labels[rows.index(r)]) in range(len(row_labels))]

# 实际筛选：只显示有事件的行/列
def has_events(row):
    return any(v > 0 for v in row)

active = [(lbl, row) for lbl, row in zip(row_labels, rows) if has_events(row)]
if not active:
    # fallback：显示全部
    active = list(zip(row_labels, rows))

labels_out = [a[0] for a in active]
rows_out   = [a[1] for a in active]

max_v = max((v for row in rows_out for v in row), default=1)
col_w = max(len(n) for n in nodes) if nodes else 6
lbl_w = max(len(l) for l in labels_out) if labels_out else 8

# 列标题
print("\nPrimeLog · Error Heatmap  (caller → callee)\n")
header_short = [n.split('.')[-1] for n in nodes]
print(" " * (lbl_w + 2) + "  ".join(f"{h:>{col_w}}" for h in header_short))
print(" " * (lbl_w + 2) + "  ".join("─" * col_w for _ in nodes))

for lbl, row in zip(labels_out, rows_out):
    short = lbl.split('.')[-1]
    cells = []
    for v in row[:len(nodes)]:
        c = val_to_char(v, max_v)
        # 数值标注
        label = f"{v:.1f}" if v > 0 else " "
        cells.append(f"{c}{label:>{col_w-1}}")
    print(f"{short:>{lbl_w}} │ " + "  ".join(cells))

print()
print(f"  scale: {CHARS[0]}=0  →  {CHARS[-1]}={max_v:.2f}")
print()
