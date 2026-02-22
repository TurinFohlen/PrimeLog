#!/usr/bin/env python3
"""stats_advanced.py — 错误分布统计（函数化版本）"""

import json
import glob
import os
from collections import Counter


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


def run(log_dir: str = None, log_file: str = None, top: int = 10) -> None:
    """打印错误分布统计。"""
    _dir = log_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )
    lf = log_file or find_latest(_dir, "error_events_*.json")
    af = find_latest(_dir, "adjacency_matrix_*.json")

    if not lf:
        print(f"❌ 在 {_dir} 下未找到 error_events_*.json")
        return

    with open(lf) as f:
        data = json.load(f)
    nodes = []
    # 若无 adj 文件，尝试从 log_file 同目录找
    if not af and log_file:
        import glob as _g
        _d = os.path.dirname(os.path.abspath(log_file))
        _m = _g.glob(os.path.join(_d, "adjacency_matrix_*.json"))
        af = max(_m, key=os.path.getmtime) if _m else None
    if af:
        with open(af) as f2:
            nodes = json.load(f2)['nodes']

    rev_map       = {v: k for k, v in data['prime_map'].items()}
    events        = data['events']
    total_errors  = Counter()
    caller_errors = Counter()
    callee_errors = Counter()

    for _, caller, callee, composite, _ in events:
        if composite == 1:
            continue
        errors = decode(composite, rev_map)
        cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
        ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
        for e in errors:
            total_errors[e]        += 1
            caller_errors[(cn, e)] += 1
            callee_errors[(ce, e)] += 1

    print(f"\n错误统计  ({lf})\n{'─'*60}")
    print("\n全局错误类型分布:")
    for err, cnt in total_errors.most_common():
        print(f"  {err:25s}: {cnt}")
    print(f"\n按调用者统计（Top {top}）:")
    for (comp, err), cnt in caller_errors.most_common(top):
        print(f"  {comp:35s}  {err:20s}: {cnt}")
    print(f"\n按被调用者统计（Top {top}）:")
    for (comp, err), cnt in callee_errors.most_common(top):
        print(f"  {comp:35s}  {err:20s}: {cnt}")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='统计错误分布')
    p.add_argument('--log-dir', default=None)
    p.add_argument('--file',    default=None)
    p.add_argument('--top',     type=int, default=10)
    args = p.parse_args()
    run(log_dir=args.log_dir, log_file=args.file, top=args.top)
