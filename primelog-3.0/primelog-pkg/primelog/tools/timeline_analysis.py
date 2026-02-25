#!/usr/bin/env python3
"""
timeline_analysis.py - 基于时间戳的错误事件分析（示例）
用法：python timeline_analysis.py <error_events.json>
"""
import json
import sys
from datetime import datetime
from collections import Counter

def main():
    if len(sys.argv) != 2:
        print("用法: python timeline_analysis.py <error_events.json>")
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        data = json.load(f)
    
    timestamps = data.get('timestamps', [])
    events = data['events']
    prime_map = data['prime_map']
    rev_map = {v:k for k,v in prime_map.items()}
    
    # 将时间戳解析为 datetime 对象
    start_ts_str = data.get('metadata', {}).get('start_timestamp', '')
    if timestamps and isinstance(timestamps[0], float) and start_ts_str:
        from datetime import timedelta
        start_dt = datetime.fromisoformat(start_ts_str)
        dt_list = [start_dt + timedelta(seconds=t) for t in timestamps]
    elif timestamps and isinstance(timestamps[0], str):
        dt_list = [datetime.fromisoformat(ts) for ts in timestamps]
    else:
        dt_list = []
    
    # 按分钟统计事件数量
    minute_counts = Counter()
    for dt in dt_list:
        minute = dt.strftime("%Y-%m-%d %H:%M")
        minute_counts[minute] += 1
    
    print("每分钟事件数（前10）：")
    for minute, cnt in sorted(minute_counts.items())[:10]:
        print(f"  {minute}: {cnt}")
    
    # 可以继续分析错误类型的时间分布
    # ...

if __name__ == "__main__":
    main()

def run(log_file: str) -> None:
    """Orchestrator 可编程调用入口"""
    with open(log_file) as f:
        data = json.load(f)
    timestamps = data.get('timestamps', [])
    events = data['events']
    prime_map = data['prime_map']
    rev_map = {v: k for k, v in prime_map.items()}
    start_ts_str = data.get('metadata', {}).get('start_timestamp', '')
    if timestamps and isinstance(timestamps[0], float) and start_ts_str:
        from datetime import timedelta
        start_dt = datetime.fromisoformat(start_ts_str)
        dt_list = [start_dt + timedelta(seconds=t) for t in timestamps]
    elif timestamps and isinstance(timestamps[0], str):
        dt_list = [datetime.fromisoformat(ts) for ts in timestamps]
    else:
        dt_list = []
    minute_counts = Counter()
    for dt in dt_list:
        minute_counts[dt.strftime("%Y-%m-%d %H:%M")] += 1
    print(f"\n⏱️  时间线分析  ({log_file})\n{'─'*50}")
    print("每分钟事件数：")
    for minute, cnt in sorted(minute_counts.items()):
        bar = '█' * min(cnt, 40)
        print(f"  {minute}: {bar} {cnt}")
    print(f"{'─'*50}\n总计 {len(events)} 条事件，跨 {len(minute_counts)} 分钟")
