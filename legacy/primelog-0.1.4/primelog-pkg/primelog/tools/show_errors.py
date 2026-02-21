import json
import glob
import os

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

def _find_latest(pattern):
    files = glob.glob(os.path.join(_LOG_DIR, pattern))
    if not files:
        raise FileNotFoundError(f"在 {_LOG_DIR} 下未找到匹配 {pattern} 的文件")
    return max(files, key=os.path.getmtime)

log_file = _find_latest("error_events_*.json")
adj_file = _find_latest("adjacency_matrix_*.json")

with open(adj_file) as f:
    nodes = json.load(f)['nodes']

with open(log_file) as f:
    data = json.load(f)
    prime_map = data['prime_map']
    rev_map = {v: k for k, v in prime_map.items()}
    events = data['events']

print("错误事件详情（t, 调用者, 被调用者, 复合值, 解码错误）")
for t, caller, callee, composite, log_val in events:
    if composite == 1:
        continue
    remaining = composite
    errors = []
    for p, name in rev_map.items():
        if p > 1 and remaining % p == 0:
            errors.append(name)
            while remaining % p == 0:
                remaining //= p
    if remaining > 1:
        errors.append('unknown_prime')
    print(f"t={t:4d} {nodes[caller]:30s} → {nodes[callee]:30s} comp={composite:3d} log={log_val:7.4f} errors={errors}")
