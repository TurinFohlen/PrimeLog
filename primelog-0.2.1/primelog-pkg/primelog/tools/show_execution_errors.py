#!/usr/bin/env python3
"""show_execution_errors.py — 仅显示执行期错误（非 none）事件"""

import json
import glob
import os


def find_latest(log_dir: str, pattern: str):
    files = glob.glob(os.path.join(log_dir, pattern))
    return max(files, key=os.path.getmtime) if files else None


def run(log_dir: str = None, log_file: str = None, adj_file: str = None) -> None:
    _dir = log_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )
    lf = log_file or find_latest(_dir, "error_events_*.json")
    if not adj_file and lf:
        _sd = os.path.dirname(os.path.abspath(lf))
        adj_file = find_latest(_sd, "adjacency_matrix_*.json")
    af = adj_file or find_latest(_dir, "adjacency_matrix_*.json")

    if not lf or not af:
        print(f"❌ 在 {_dir} 下未找到日志文件")
        return

    with open(lf) as f:
        log = json.load(f)
    with open(af) as f:
        adj = json.load(f)

    nodes      = adj['nodes']
    events     = log['events']
    rev_map    = {v: k for k, v in log['prime_map'].items()}
    timestamps = log.get('timestamps', [])

    exec_errors = [(i, e) for i, e in enumerate(events) if e[3] != 1]

    print(f"\n执行期错误事件  ({lf})\n{'─'*70}")
    if not exec_errors:
        print("  ✅ 无执行期错误")
    for i, (t, caller, callee, composite, _) in exec_errors:
        remaining = composite
        errors = []
        for p, name in rev_map.items():
            if p > 1 and remaining % p == 0:
                errors.append(name)
                while remaining % p == 0:
                    remaining //= p
        ts = timestamps[i] if i < len(timestamps) else ""
        cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
        ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
        print(f"t={t:4d}  {cn:35s} → {ce:35s}")
        print(f"       errors={errors}  {ts}")
    print(f"{'─'*70}\n共 {len(exec_errors)} 个执行期错误（总事件 {len(events)} 条）")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--log-dir', default=None)
    p.add_argument('--file',    default=None)
    p.add_argument('--adj',     default=None)
    args = p.parse_args()
    run(log_dir=args.log_dir, log_file=args.file, adj_file=args.adj)
