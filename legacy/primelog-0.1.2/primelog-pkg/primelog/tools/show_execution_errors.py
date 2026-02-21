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

with open(log_file) as f:
    log = json.load(f)
with open(adj_file) as f:
    adj = json.load(f)

prime_map = log['prime_map']
rev_map = {v: k for k, v in prime_map.items()}
nodes = adj['nodes']

print("execution_error 事件详情：")
for event in log['events']:
    t, caller, callee, composite, log_val = event
    if composite == 19:
        print(f"  事件 {t}: 调用者 {nodes[caller]} -> 被调用者 {nodes[callee]}")
