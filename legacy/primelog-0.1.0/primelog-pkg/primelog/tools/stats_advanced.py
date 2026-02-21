import json
import glob
import os
from collections import Counter

# 自动查找最新日志（相对于本文件所在目录的上级 logs 目录）
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
log_files = glob.glob(os.path.join(log_dir, "error_events_*.json"))
if not log_files:
    print("未找到错误日志文件")
    exit(1)
latest_log = max(log_files, key=os.path.getmtime)
print(f"使用日志文件: {latest_log}")

# 对应的邻接矩阵（取相同时间戳的，如果没有则用最新的）
base = latest_log.replace("error_events_", "adjacency_matrix_")
if os.path.exists(base):
    adj_file = base
else:
    adj_files = glob.glob(os.path.join(log_dir, "adjacency_matrix_*.json"))
    adj_file = max(adj_files, key=os.path.getmtime) if adj_files else None
    if not adj_file:
        print("未找到邻接矩阵文件")
        exit(1)
print(f"使用邻接矩阵: {adj_file}")

with open(latest_log) as f:
    data = json.load(f)
prime_map = data['prime_map']
rev_map = {v: k for k, v in prime_map.items()}
events = data['events']

with open(adj_file) as f:
    adj_data = json.load(f)
nodes = adj_data['nodes']  # 组件名列表，索引从0开始

caller_errors = Counter()
callee_errors = Counter()

for t, caller, callee, composite, log_val in events:
    if composite == 1:
        continue
    # 解码错误类型
    remaining = composite
    errors = []
    for p, name in rev_map.items():
        if p > 1 and remaining % p == 0:
            errors.append(name)
            while remaining % p == 0:
                remaining //= p
    if remaining > 1:
        errors.append('unknown_prime')
    for err in errors:
        caller_errors[(nodes[caller], err)] += 1
        callee_errors[(nodes[callee], err)] += 1

print("\n按调用者统计错误：")
for (comp, err), cnt in caller_errors.most_common():
    print(f"  {comp:30s} {err:20s}: {cnt}")

print("\n按被调用者统计错误：")
for (comp, err), cnt in callee_errors.most_common():
    print(f"  {comp:30s} {err:20s}: {cnt}")