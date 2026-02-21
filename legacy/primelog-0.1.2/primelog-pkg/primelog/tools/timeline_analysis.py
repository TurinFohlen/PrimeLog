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
    dt_list = [datetime.fromisoformat(ts) for ts in timestamps]
    
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