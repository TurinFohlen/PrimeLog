#!/usr/bin/env python3
"""
exporter.py - 将 PrimeLog 数据导出为其他分析工具可用的格式
支持格式：
  - csv      : 逗号分隔值，可用 Excel、Pandas、Splunk 等导入
  - jsonl    : JSON Lines，每行一个事件，适合流式处理
  - elastic  : Elasticsearch Bulk API 格式，可直接导入

新增特性：
  - 支持 --raw 选项，不解码错误，直接输出原始 log_value（适合数学分析）
  - 自动从同目录邻接矩阵注入组件名（nodes）
  - 统一的 run() 接口，与 orchestrator 集成

用法：
    primelog convert --project my-proj --format csv --output events.csv
    primelog convert --project my-proj --format csv --raw --output raw.csv
    python exporter.py error_events.json --format jsonl --output events.jsonl
"""

import json
import csv
import sys
import argparse
import os
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

# 导入公共工具函数
from primelog.tools.common import decode_event, get_composite, find_latest_log


def _inject_nodes(data: Dict, log_file: str) -> Dict:
    """
    如果 data 中没有 nodes，尝试从同目录的 adjacency_matrix 文件中注入。
    返回注入后的 data（原地修改并返回）。
    """
    if 'nodes' in data and data['nodes']:
        return data

    log_dir = os.path.dirname(os.path.abspath(log_file))
    matches = glob.glob(os.path.join(log_dir, "adjacency_matrix_*.json"))
    if matches:
        # 取最新的
        latest_adj = max(matches, key=os.path.getmtime)
        try:
            with open(latest_adj, 'r', encoding='utf-8') as f:
                adj_data = json.load(f)
                nodes = adj_data.get('nodes', [])
                if nodes:
                    data['nodes'] = nodes
                    print(f"ℹ️ 从 {latest_adj} 注入 nodes 信息", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ 读取邻接矩阵失败，将使用索引代替组件名: {e}", file=sys.stderr)
    else:
        print("⚠️ 未找到邻接矩阵文件，将使用索引代替组件名", file=sys.stderr)
    return data


def load_log(log_file: str) -> Dict[str, Any]:
    """加载日志文件并自动注入 nodes"""
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"日志文件不存在: {log_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"日志文件不是有效的 JSON: {e}")

    # 注入 nodes
    data = _inject_nodes(data, log_file)
    return data


def filter_events(
    data: Dict,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    error_types: Optional[List[str]] = None,
    component: Optional[str] = None,
    decode: bool = True
) -> List[Dict]:
    """
    根据条件过滤事件。
    返回的每个事件包含：
        timestamp, caller_index, callee_index, composite, log_value,
        errors (如果 decode=True), caller_name, callee_name
    """
    events = data['events']
    timestamps = data.get('timestamps', [])
    prime_map = data['prime_map']
    nodes = data.get('nodes', [])

    filtered = []
    for i, event in enumerate(events):
        # 时间戳
        ts = timestamps[i] if i < len(timestamps) else None
        if ts:
            if start_time and ts < start_time.isoformat():
                continue
            if end_time and ts > end_time.isoformat():
                continue

        # 提取原始值
        raw_value = event[3]                     # 可能是 log_value (float) 或 composite (int)
        composite = get_composite(event)          # 总是获取整数乘积
        log_value = raw_value if isinstance(raw_value, float) else None

        # 解码错误（如果需要）
        errors = None
        if decode:
            errors = decode_event(event, prime_map)

        # 错误类型过滤
        if error_types and errors:
            if not any(e in error_types for e in errors):
                continue

        # 组件过滤（涉及 caller 或 callee）
        caller_name = nodes[event[1]] if event[1] < len(nodes) else f"#{event[1]}"
        callee_name = nodes[event[2]] if event[2] < len(nodes) else f"#{event[2]}"
        if component:
            if component not in (caller_name, callee_name):
                continue

        filtered.append({
            'timestamp': ts,
            'caller_index': event[1],
            'callee_index': event[2],
            'caller_name': caller_name,
            'callee_name': callee_name,
            'composite': composite,
            'log_value': log_value,
            'errors': errors,               # None 如果 decode=False
        })
    return filtered


def export_csv(events: List[Dict], output_file: str, raw: bool = False):
    """导出为 CSV 文件"""
    fieldnames = ['timestamp', 'caller', 'callee', 'composite']
    if not raw:
        fieldnames.append('errors')
    else:
        fieldnames.append('log_value')

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            row = {
                'timestamp': e['timestamp'],
                'caller': e['caller_name'],
                'callee': e['callee_name'],
                'composite': e['composite'],
            }
            if not raw:
                row['errors'] = '|'.join(e['errors']) if e['errors'] else ''
            else:
                row['log_value'] = e['log_value'] if e['log_value'] is not None else ''
            writer.writerow(row)
    print(f"✅ 已导出 {len(events)} 条事件到 CSV: {output_file}")


def export_jsonl(events: List[Dict], output_file: str, raw: bool = False):
    """导出为 JSON Lines 格式（每行一个 JSON）"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for e in events:
            # 根据 raw 决定是否移除 errors 字段
            out = e.copy()
            if raw:
                out.pop('errors', None)
            else:
                out.pop('log_value', None)   # 不输出原始值
            # 确保可序列化
            f.write(json.dumps(out, ensure_ascii=False) + '\n')
    print(f"✅ 已导出 {len(events)} 条事件到 JSONL: {output_file}")


def export_elastic(events: List[Dict], output_file: str, index: str = 'primelog', raw: bool = False):
    """导出为 Elasticsearch Bulk API 格式"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for e in events:
            doc = e.copy()
            if raw:
                doc.pop('errors', None)
            else:
                doc.pop('log_value', None)
            # 去除 None 值
            doc = {k: v for k, v in doc.items() if v is not None}
            action = {"index": {"_index": index}}
            f.write(json.dumps(action, ensure_ascii=False) + '\n')
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    print(f"✅ 已导出 {len(events)} 条事件到 Elastic Bulk 文件: {output_file}")


def run(
    log_file: str = "",
    project: str = "",
    log_dir: str = "",
    fmt: str = "csv",
    output: str = "",
    index: str = "primelog",
    start: str = "",
    end: str = "",
    error_types: str = "",
    component: str = "",
    raw: bool = False,
) -> None:
    """
    统一的运行入口，供 orchestrator 调用。
    参数说明：
        log_file   : 指定日志文件路径（如果为空，则根据 project/log_dir 自动查找最新）
        project    : 项目名（用于自动查找）
        log_dir    : 日志根目录（默认 ./logs）
        fmt        : 导出格式（csv/jsonl/elastic）
        output     : 输出文件路径（自动生成若为空）
        index      : Elasticsearch 索引名
        start/end  : ISO 格式时间范围
        error_types: 逗号分隔的错误类型
        component  : 组件名（筛选涉及该组件的事件）
        raw        : 若为 True，不解码错误，保留原始 log_value
    """
    # 自动定位日志文件
    if not log_file and project:
        log_dir = log_dir or "./logs"
        log_file = find_latest_log(log_dir, project, "error_events_*.json")
        if not log_file:
            print(f"❌ 在 {log_dir}/{project} 下未找到 error_events_*.json")
            return
    elif not log_file:
        print("❌ 必须指定 log_file 或 project")
        return

    # 加载数据
    try:
        data = load_log(log_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}")
        return

    # 解析时间
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    error_list = error_types.split(',') if error_types else None

    # 过滤事件
    events = filter_events(
        data,
        start_time=start_dt,
        end_time=end_dt,
        error_types=error_list,
        component=component or None,
        decode=not raw   # decode 与 raw 相反
    )

    if not events:
        print("⚠️ 没有符合条件的事件")
        return

    # 确定输出文件名
    if not output:
        base = Path(log_file).stem
        if fmt == 'elastic':
            output = f"{base}.bulk.json"
        else:
            output = f"{base}.{fmt}"

    # 导出
    if fmt == 'csv':
        export_csv(events, output, raw)
    elif fmt == 'jsonl':
        export_jsonl(events, output, raw)
    elif fmt == 'elastic':
        export_elastic(events, output, index, raw)
    else:
        print(f"❌ 不支持的格式: {fmt}")


def main():
    parser = argparse.ArgumentParser(
        description="PrimeLog 数据导出器 - 对接外部分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input', nargs='?', help='输入的 error_events_*.json 文件路径（若不指定则需 --project）')
    parser.add_argument('--project', help='项目名（与 --log-dir 一起用于自动查找最新日志）')
    parser.add_argument('--log-dir', default='./logs', help='日志根目录（默认 ./logs）')
    parser.add_argument('--format', '-f', choices=['csv', 'jsonl', 'elastic'],
                        default='csv', help='导出格式（默认：csv）')
    parser.add_argument('--output', '-o', help='输出文件路径（默认根据输入文件名自动生成）')
    parser.add_argument('--index', default='primelog',
                        help='Elasticsearch 索引名（仅 elastic 格式有效，默认：primelog）')
    parser.add_argument('--start', help='起始时间，ISO 格式，如 2026-02-20T00:00:00')
    parser.add_argument('--end', help='结束时间，ISO 格式')
    parser.add_argument('--error-types', help='只导出指定错误类型，逗号分隔，如 timeout,file_not_found')
    parser.add_argument('--component', help='只导出涉及该组件的事件（调用者或被调用者）')
    parser.add_argument('--raw', action='store_true', help='不解码错误，直接输出原始 log_value（适合数学分析）')

    args = parser.parse_args()

    # 确定日志文件
    if args.input:
        log_file = args.input
    elif args.project:
        log_file = find_latest_log(args.log_dir, args.project, "error_events_*.json")
        if not log_file:
            print(f"❌ 在 {args.log_dir}/{args.project} 下未找到 error_events_*.json")
            sys.exit(1)
    else:
        print("❌ 必须指定输入文件或 --project")
        sys.exit(1)

    run(
        log_file=log_file,
        project=args.project,          # 保留，但 run 内部未使用（已用 log_file）
        log_dir=args.log_dir,
        fmt=args.format,
        output=args.output,
        index=args.index,
        start=args.start,
        end=args.end,
        error_types=args.error_types,
        component=args.component,
        raw=args.raw,
    )


if __name__ == '__main__':
    main()