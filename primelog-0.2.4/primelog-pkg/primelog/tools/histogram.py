#!/usr/bin/env python3
"""
独立错误直方图查看器（支持对数归一化）

用法：
    python histogram.py                     # 自动查找最新日志并显示
    python histogram.py --file /path/to/error_events.json   # 指定文件
    python histogram.py --top 20             # 显示前20种错误
    python histogram.py --log                # 使用对数归一化
    python histogram.py --width 80            # 设置直方图宽度
    python histogram.py --help                # 显示帮助
"""

import json
import os
import sys
import glob
import argparse
import math
from collections import Counter
from datetime import datetime
from primelog.tools.common import get_composite


_DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

def find_latest_log(log_dir=_DEFAULT_LOG_DIR):
    """在指定目录下找到最新的 error_events_*.json 文件"""
    pattern = os.path.join(log_dir, "error_events_*.json")
    files = glob.glob(pattern)
    if not files:
        return None
    # 按文件名中的时间戳排序（格式：error_events_YYYYMMDD_HHMMSS.json）
    def extract_time(filename):
        basename = os.path.basename(filename)
        # 提取时间部分：去掉前缀和后缀
        time_str = basename.replace("error_events_", "").replace(".json", "")
        try:
            return datetime.strptime(time_str, "%Y%m%d_%H%M%S")
        except:
            return datetime.min  # 解析失败则放最后
    files.sort(key=extract_time, reverse=True)
    return files[0]


def decode_errors(composite, prime_map):
    """从复合值中解码错误类型列表"""
    if composite <= 1:
        return ["none"]
    errors = []
    remaining = composite
    # 构建素数到错误名的反向映射
    rev_map = {v: k for k, v in prime_map.items()}
    # 注意：素数可能很多，但 prime_map 通常不大
    for p in sorted(rev_map.keys()):
        if p <= 1:
            continue
        if remaining % p == 0:
            errors.append(rev_map[p])
            while remaining % p == 0:
                remaining //= p
    if remaining > 1:
        errors.append("unknown_prime")
    return errors

def print_error_histogram(stats_dict, top_n=15, width=60, log_scale=False):
    """
    打印错误分布的 ASCII 直方图（支持对数归一化）

    参数：
        stats_dict : dict, 错误统计字典，如 {'timeout': 423, 'file_not_found': 257}
        top_n      : int, 只显示次数最多的前 N 种错误
        width      : int, 直方图条形的最大字符宽度
        log_scale  : bool, 是否使用对数归一化（True 则条形长度比例 = log(cnt) / log(max_count)）
    """
    if not stats_dict:
        print("  无错误记录")
        return

    sorted_items = sorted(stats_dict.items(), key=lambda x: -x[1])[:top_n]
    max_count = max(cnt for _, cnt in sorted_items) if sorted_items else 1

    # 🔧 关键修复：统一计算 ratio（两种模式共用）
    if log_scale:
        # 对数模式：ratio = log(cnt) / log(max_count)
        log_counts = [math.log(cnt) if cnt > 0 else 0 for _, cnt in sorted_items]
        max_log = max(log_counts) if log_counts else 1
        ratios = [lc / max_log for lc in log_counts]
    else:
        # 正常模式：也用 ratio，但保持线性
        ratios = [cnt / max_count for _, cnt in sorted_items]

    # 截断错误名称（避免过长）
    max_err_display_len = 30
    truncated_errs = []
    for err, _ in sorted_items:
        if len(err) > max_err_display_len:
            truncated_errs.append(err[:max_err_display_len-3] + '...')
        else:
            truncated_errs.append(err)

    max_err_len = max(len(t_err) for t_err in truncated_errs)
    err_width = max_err_len + 2

    # 打印标题和顶部分隔线
    scale_info = " (对数归一化)" if log_scale else ""
    print(f"\n📊 错误类型分布直方图{scale_info}")
    print("-" * (err_width + width + 20))

    # 🔧 关键修复：统一渲染逻辑（两种模式共用）
    for (err, cnt), t_err, ratio in zip(sorted_items, truncated_errs, ratios):
        bar_len = int(ratio * width)
        bar = "█" * bar_len + " " * (width - bar_len)  # 补空格到满宽，确保对齐
        print(f"| {t_err:<{err_width}s} ({cnt:5d}): {bar} |")

    print("-" * (err_width + width + 20))
    if log_scale:
        print("注：条形长度使用对数归一化，以压缩极端值，便于观察整体分布。")

def main():
    parser = argparse.ArgumentParser(description="B站视频合并工具错误日志直方图查看器")
    parser.add_argument("--file", "-f", help="指定 error_events.json 文件路径")
    parser.add_argument("--top", "-t", type=int, default=15, help="显示前 N 种错误 (默认 15)")
    parser.add_argument("--width", "-w", type=int, default=60, help="直方图宽度 (默认 60)")
    parser.add_argument("--log", action="store_true", help="使用对数归一化")
    args = parser.parse_args()

    # 确定日志文件
    if args.file:
        log_file = args.file
        if not os.path.isfile(log_file):
            print(f"❌ 文件不存在: {log_file}")
            sys.exit(1)
    else:
        log_file = find_latest_log()
        if not log_file:
            print("❌ 未找到任何 error_events_*.json 文件")
            print("请确保已运行主程序并生成了日志，或使用 --file 指定路径")
            sys.exit(1)
        print(f"🔍 自动找到最新日志: {log_file}")

    # 读取 JSON
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")
        sys.exit(1)

    prime_map = data.get("prime_map", {})
    events = data.get("events", [])

    if not events:
        print("⚠️ 日志文件中没有事件记录")
        return

    # 统计错误类型出现次数
    error_counter = Counter()
    for event in events:
        # 事件格式：[t, caller, callee, log_value]（v2.0）或旧版 composite（v1.x）
        composite = get_composite(event)
        error_list = decode_errors(composite, prime_map)
        for err in error_list:
            if err != "none":  # 忽略无错误事件
                error_counter[err] += 1

    # 打印直方图
    print_error_histogram(error_counter, top_n=args.top, width=args.width, log_scale=args.log)

    # 显示一些额外信息
    print(f"\n📈 总事件数: {len(events)}")
    print(f"📁 日志文件: {log_file}")


if __name__ == "__main__":
    main()

def run(log_file: str = "", log_dir: str = "", top: int = 15,
        width: int = 60, log_scale: bool = False) -> None:
    """Orchestrator 可编程调用入口"""
    import glob, os
    if not log_file:
        search_dir = log_dir or _DEFAULT_LOG_DIR
        log_file = find_latest_log(search_dir)
        if not log_file:
            print(f"❌ 在 {search_dir} 下未找到 error_events_*.json")
            return
        print(f"🔍 自动找到最新日志: {log_file}")
    with open(log_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    error_counter = Counter()
    for event in data.get("events", []):
        composite = get_composite(event)
        for err in decode_errors(composite, data.get("prime_map", {})):
            if err != "none":
                error_counter[err] += 1
    print_error_histogram(error_counter, top_n=top, width=width, log_scale=log_scale)
    print(f"\n📈 总事件数: {len(data.get('events', []))}\n📁 日志文件: {log_file}")
