#!/usr/bin/env python3
"""show_errors.py — 错误事件详情查看器（函数化版本）"""

import json
import glob
import os


def find_latest(log_dir: str, pattern: str):
    files = glob.glob(os.path.join(log_dir, pattern))
    return max(files, key=os.path.getmtime) if files else None


def decode(composite: int, rev_map: dict) -> list:
    remaining = composite
    errors = []
    for p, name in rev_map.items():
        if p > 1 and remaining % p == 0:
            errors.append(name)
            while remaining % p == 0:
                remaining //= p
    return errors or ['unknown']


def run(log_dir: str = None, log_file: str = None, adj_file: str = None) -> None:
    """打印错误事件详情。log_dir 优先自动查找，也可直接传 log_file/adj_file。"""
    _dir = log_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )
    lf = log_file or find_latest(_dir, "error_events_*.json")
    # adj 优先从 log_file 同目录找，再从 log_dir 找
    if not adj_file and lf:
        _same_dir = os.path.dirname(os.path.abspath(lf))
        adj_file = find_latest(_same_dir, "adjacency_matrix_*.json")
    af = adj_file or find_latest(_dir, "adjacency_matrix_*.json")

    if not lf:
        print(f"❌ 在 {_dir} 下未找到 error_events_*.json")
        return
    if not af:
        print(f"❌ 在 {_dir} 下未找到 adjacency_matrix_*.json")
        return

    with open(af) as f:
        nodes = json.load(f)['nodes']
    with open(lf) as f:
        data = json.load(f)

    rev_map    = {v: k for k, v in data['prime_map'].items()}
    events     = data['events']
    timestamps = data.get('timestamps', [])

    error_count = 0
    print(f"\n错误事件详情  ({lf})\n{'─'*70}")
    for i, (t, caller, callee, composite, _) in enumerate(events):
        if composite == 1:
            continue
        error_count += 1
        errors = decode(composite, rev_map)
        ts = timestamps[i] if i < len(timestamps) else ""
        cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
        ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
        print(f"t={t:4d}  {cn:35s} → {ce:35s}")
        print(f"       errors={errors}  composite={composite}  {ts}")

    if error_count == 0:
        print("  ✅ 无错误事件")
    print(f"{'─'*70}\n共 {error_count} 个错误事件（总事件 {len(events)} 条）")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='显示错误事件详情')
    p.add_argument('--log-dir',  default=None)
    p.add_argument('--file',     default=None)
    p.add_argument('--adj',      default=None)
    args = p.parse_args()
    run(log_dir=args.log_dir, log_file=args.file, adj_file=args.adj)
