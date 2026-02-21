#!/usr/bin/env python3
"""
exporter.py - 将 PrimeLog 数据导出为其他分析工具可用的格式
支持格式：
  - csv      : 逗号分隔值，可用 Excel、Pandas、Splunk 等导入
  - jsonl    : JSON Lines，每行一个事件，适合流式处理
  - elastic  : Elasticsearch Bulk API 格式，可直接导入

用法：
    python exporter.py <error_events.json> --format csv --output events.csv
    python exporter.py <error_events.json> --format jsonl --output events.jsonl
    python exporter.py <error_events.json> --format elastic --output bulk.json --index primelog

可选过滤：
    --start 2026-02-20T00:00:00      # 起始时间（ISO 格式）
    --end 2026-02-21T23:59:59        # 结束时间
    --error-types timeout,file_not_found  # 只导出指定错误类型（逗号分隔）
    --component component_name        # 只导出涉及该组件的事件
"""

import json
import csv
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到路径，以便导入 core
sys.path.insert(0, str(Path(__file__).parent.parent))
from primelog.core.error_log import decode_errors

def load_log(log_file: str) -> Dict[str, Any]:
    """加载日志文件"""
    with open(log_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def filter_events(data: Dict, start_time=None, end_time=None,
                  error_types=None, component=None) -> List[Dict]:
    """
    根据条件过滤事件
    返回的每个事件包含：
        timestamp, caller_index, callee_index, composite,
        errors (列表), caller_name, callee_name
    """
    events = data['events']
    timestamps = data.get('timestamps', [])
    prime_map = data['prime_map']
    nodes = data.get('nodes', [])

    filtered = []
    for i, event in enumerate(events):
        # 时间戳
        ts = timestamps[i] if i < len(timestamps) else None
        if start_time and ts and ts < start_time:
            continue
        if end_time and ts and ts > end_time:
            continue

        # 解码错误
        composite = event[3]
        errors = decode_errors(composite, prime_map)

        # 错误类型过滤
        if error_types and not any(e in error_types for e in errors):
            continue

        # 组件过滤（涉及 caller 或 callee）
        caller_name = nodes[event[1]] if event[1] < len(nodes) else None
        callee_name = nodes[event[2]] if event[2] < len(nodes) else None
        if component and component not in (caller_name, callee_name):
            continue

        filtered.append({
            'timestamp': ts,
            'caller_index': event[1],
            'callee_index': event[2],
            'caller_name': caller_name,
            'callee_name': callee_name,
            'composite': composite,
            'errors': errors,
        })
    return filtered

def export_csv(events: List[Dict], output_file):
    """导出为 CSV 文件"""
    fieldnames = ['timestamp', 'caller', 'callee', 'composite', 'errors']
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            writer.writerow({
                'timestamp': e['timestamp'],
                'caller': e['caller_name'],
                'callee': e['callee_name'],
                'composite': e['composite'],
                'errors': '|'.join(e['errors'])
            })
    print(f"✅ 已导出 {len(events)} 条事件到 CSV: {output_file}")

def export_jsonl(events: List[Dict], output_file):
    """导出为 JSON Lines 格式（每行一个 JSON）"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    print(f"✅ 已导出 {len(events)} 条事件到 JSONL: {output_file}")

def export_elastic(events: List[Dict], output_file, index='primelog'):
    """
    导出为 Elasticsearch Bulk API 格式
    生成两个 action 行和一个 data 行，参考：
        {"index":{"_index":"primelog"}}
        {"timestamp":"...","caller":"...",...}
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for e in events:
            # 去掉可能引起 Elasticsearch 歧义的字段（如 None）
            doc = {k: v for k, v in e.items() if v is not None}
            # 将 errors 列表转换为字符串或保留为数组（ES 支持）
            doc['errors'] = doc['errors']
            action = {"index": {"_index": index}}
            f.write(json.dumps(action, ensure_ascii=False) + '\n')
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    print(f"✅ 已导出 {len(events)} 条事件到 Elastic Bulk 文件: {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description="PrimeLog 数据导出器 - 对接外部分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input', help='输入的 error_events_*.json 文件路径')
    parser.add_argument('--format', '-f', choices=['csv', 'jsonl', 'elastic'],
                        default='csv', help='导出格式（默认：csv）')
    parser.add_argument('--output', '-o', help='输出文件路径（默认：根据输入文件名自动生成）')
    parser.add_argument('--index', default='primelog',
                        help='Elasticsearch 索引名（仅 elastic 格式有效，默认：primelog）')
    parser.add_argument('--start', help='起始时间，ISO 格式，如 2026-02-20T00:00:00')
    parser.add_argument('--end', help='结束时间，ISO 格式')
    parser.add_argument('--error-types', help='只导出指定错误类型，逗号分隔，如 timeout,file_not_found')
    parser.add_argument('--component', help='只导出涉及该组件的事件（调用者或被调用者）')

    args = parser.parse_args()

    # 加载日志
    try:
        data = load_log(args.input)
    except Exception as e:
        print(f"❌ 读取日志失败: {e}")
        sys.exit(1)

    # 解析时间
    start = datetime.fromisoformat(args.start) if args.start else None
    end = datetime.fromisoformat(args.end) if args.end else None
    error_types = args.error_types.split(',') if args.error_types else None

    # 过滤
    events = filter_events(data, start, end, error_types, args.component)

    if not events:
        print("⚠️ 没有符合条件的事件")
        return

    # 确定输出文件名
    if args.output:
        out_path = args.output
    else:
        base = Path(args.input).stem
        out_path = f"{base}.{args.format}"
        if args.format == 'elastic':
            out_path = f"{base}.bulk.json"

    # 导出
    if args.format == 'csv':
        export_csv(events, out_path)
    elif args.format == 'jsonl':
        export_jsonl(events, out_path)
    elif args.format == 'elastic':
        export_elastic(events, out_path, args.index)

if __name__ == '__main__':
    main()