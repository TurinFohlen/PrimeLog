#!/usr/bin/env python3
"""
timeline_visualization.py - 基于时间戳的错误事件ASCII可视化工具（网安版）

功能：
- 时间轴热力图（Heatmap）：按小时/分钟显示事件密度
- 事件冲击波图：显示突发性错误的分布
- 错误类型时间线：多层叠加显示不同错误类型的时序
- 攻击检测模式：识别异常流量模式（突然爆发）

用法：
    python timeline_visualization.py <error_events.json>                 # 基础分析
    python timeline_visualization.py <error_events.json> --mode heatmap  # 热力图
    python timeline_visualization.py <error_events.json> --mode wave     # 冲击波图
    python timeline_visualization.py <error_events.json> --mode timeline # 多错误时间线
    python timeline_visualization.py <error_events.json> --interval 5m   # 5分钟粒度
    python timeline_visualization.py <error_events.json> --top 5         # 只显示前5种错误
"""

import json
import sys
import argparse
import math
from datetime import datetime, timedelta
from collections import Counter, defaultdict


def decode_errors(composite, prime_map):
    """从复合值中解码错误类型列表"""
    if composite <= 1:
        return ["none"]
    errors = []
    remaining = composite
    rev_map = {v: k for k, v in prime_map.items()}
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


def parse_interval(interval_str):
    """解析时间间隔字符串，如 '5m', '1h', '30s'"""
    if interval_str.endswith('s'):
        return timedelta(seconds=int(interval_str[:-1]))
    elif interval_str.endswith('m'):
        return timedelta(minutes=int(interval_str[:-1]))
    elif interval_str.endswith('h'):
        return timedelta(hours=int(interval_str[:-1]))
    else:
        raise ValueError(f"无效的间隔格式: {interval_str}，应为 '5m', '1h', '30s' 等")


def get_time_buckets(dt_list, interval):
    """将时间戳分桶"""
    if not dt_list:
        return []
    
    start_time = min(dt_list)
    end_time = max(dt_list)
    
    buckets = []
    current = start_time
    while current <= end_time:
        buckets.append(current)
        current += interval
    
    return buckets


def print_heatmap(dt_list, interval=timedelta(minutes=5), width=60, height=20):
    """
    打印时间轴热力图
    
    参数：
        dt_list: datetime 对象列表
        interval: 时间分桶间隔
        width: 图表宽度（字符）
        height: 图表高度（行数）
    """
    if not dt_list:
        print("  无事件数据")
        return
    
    buckets = get_time_buckets(dt_list, interval)
    bucket_counts = Counter()
    
    # 统计每个桶的事件数
    for dt in dt_list:
        for i, bucket_time in enumerate(buckets):
            if dt >= bucket_time and (i == len(buckets)-1 or dt < buckets[i+1]):
                bucket_counts[bucket_time] += 1
                break
    
    max_count = max(bucket_counts.values()) if bucket_counts else 1
    
    # ASCII 热力图字符（从低到高密度）
    heatmap_chars = [' ', '░', '▒', '▓', '█']
    
    print(f"\n🔥 时间轴热力图（间隔: {interval}）")
    print("=" * (width + 20))
    
    # 计算每行显示的时间范围
    buckets_per_row = max(1, len(buckets) // height)
    
    start_time = buckets[0] if buckets else datetime.now()
    end_time = buckets[-1] if buckets else datetime.now()
    
    for row in range(height):
        start_idx = row * buckets_per_row
        end_idx = min(start_idx + buckets_per_row, len(buckets))
        
        if start_idx >= len(buckets):
            break
        
        row_buckets = buckets[start_idx:end_idx]
        row_time = row_buckets[0].strftime("%H:%M")
        
        # 计算这一行的热力值
        row_str = ""
        for bucket in row_buckets:
            count = bucket_counts.get(bucket, 0)
            ratio = count / max_count if max_count > 0 else 0
            char_idx = int(ratio * (len(heatmap_chars) - 1))
            row_str += heatmap_chars[char_idx]
        
        # 补齐到固定宽度
        row_str = row_str[:width] + ' ' * max(0, width - len(row_str))
        
        # 显示这一行的峰值
        max_in_row = max([bucket_counts.get(b, 0) for b in row_buckets])
        print(f"{row_time} |{row_str}| {max_in_row:4d}")
    
    print("=" * (width + 20))
    print(f"时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} → {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"峰值: {max_count} 事件")


def print_wave_chart(dt_list, interval=timedelta(minutes=1), width=80, height=15):
    """
    打印冲击波图（显示事件爆发）
    
    参数：
        dt_list: datetime 对象列表
        interval: 时间分桶间隔
        width: 图表宽度
        height: 图表高度
    """
    if not dt_list:
        print("  无事件数据")
        return
    
    buckets = get_time_buckets(dt_list, interval)
    bucket_counts = Counter()
    
    for dt in dt_list:
        for i, bucket_time in enumerate(buckets):
            if dt >= bucket_time and (i == len(buckets)-1 or dt < buckets[i+1]):
                bucket_counts[bucket_time] += 1
                break
    
    max_count = max(bucket_counts.values()) if bucket_counts else 1
    
    print(f"\n🌊 事件冲击波图（间隔: {interval}）")
    print("=" * width)
    
    # 选择要显示的时间点（均匀采样到 width）
    display_buckets = []
    if len(buckets) <= width:
        display_buckets = buckets
    else:
        step = len(buckets) / width
        display_buckets = [buckets[int(i * step)] for i in range(width)]
    
    # 绘制波形图（从上到下）
    for level in range(height, 0, -1):
        line = ""
        threshold = (level / height) * max_count
        
        for bucket in display_buckets:
            count = bucket_counts.get(bucket, 0)
            if count >= threshold:
                # 根据密度选择字符
                if count > max_count * 0.8:
                    line += "█"
                elif count > max_count * 0.5:
                    line += "▓"
                elif count > max_count * 0.3:
                    line += "▒"
                else:
                    line += "░"
            else:
                line += " "
        
        # 显示 Y 轴刻度
        y_label = f"{int(threshold):4d} |"
        print(y_label + line)
    
    # X 轴时间标签
    print("      " + "-" * width)
    if display_buckets:
        start_time = display_buckets[0].strftime("%H:%M")
        mid_time = display_buckets[len(display_buckets)//2].strftime("%H:%M")
        end_time = display_buckets[-1].strftime("%H:%M")
        
        # 计算标签位置
        label_start = " " * 6 + start_time
        label_mid = " " * (width//2 - len(mid_time)//2 + 6) + mid_time
        label_end = " " * (width - len(end_time) + 6) + end_time
        
        print(label_start)
        print(label_mid)
        print(label_end)
    
    print("=" * width)
    print(f"峰值: {max_count} 事件，检测到 {len([c for c in bucket_counts.values() if c > max_count * 0.5])} 个高峰区间")


def print_multi_timeline(events_data, prime_map, interval=timedelta(minutes=5), 
                        width=80, top_n=5, timestamps=None):
    """
    打印多错误类型时间线（叠加显示）
    
    参数：
        events_data: 原始事件数据列表
        prime_map: 错误类型到素数的映射
        interval: 时间分桶间隔
        width: 图表宽度
        top_n: 显示前 N 种错误类型
        timestamps: 时间戳列表
    """
    if not events_data or not timestamps:
        print("  无事件数据")
        return
    
    # 解析所有事件的错误类型
    error_timeline = defaultdict(list)  # {error_type: [dt1, dt2, ...]}
    
    for event, ts in zip(events_data, timestamps):
        dt = datetime.fromisoformat(ts)
        composite = event[3]
        errors = decode_errors(composite, prime_map)
        for err in errors:
            if err != "none":
                error_timeline[err].append(dt)
    
    # 选择出现次数最多的错误类型
    error_counts = {err: len(dts) for err, dts in error_timeline.items()}
    top_errors = sorted(error_counts.items(), key=lambda x: -x[1])[:top_n]
    
    if not top_errors:
        print("  无错误记录")
        return
    
    print(f"\n📊 多错误类型时间线（间隔: {interval}，前 {top_n} 种错误）")
    print("=" * (width + 30))
    
    # 获取时间范围
    all_times = [dt for dts in error_timeline.values() for dt in dts]
    buckets = get_time_buckets(all_times, interval)
    
    # 不同错误类型用不同符号
    symbols = ['●', '■', '▲', '◆', '★', '✦', '◉', '▣', '▼']
    
    # 为每种错误创建时间桶计数
    error_buckets = {}
    for err, _ in top_errors:
        bucket_counts = Counter()
        for dt in error_timeline[err]:
            for i, bucket_time in enumerate(buckets):
                if dt >= bucket_time and (i == len(buckets)-1 or dt < buckets[i+1]):
                    bucket_counts[bucket_time] += 1
                    break
        error_buckets[err] = bucket_counts
    
    # 选择要显示的时间点
    display_buckets = []
    if len(buckets) <= width:
        display_buckets = buckets
    else:
        step = len(buckets) / width
        display_buckets = [buckets[int(i * step)] for i in range(width)]
    
    # 打印每种错误的时间线
    for idx, (err, count) in enumerate(top_errors):
        symbol = symbols[idx % len(symbols)]
        err_display = err[:20] + '...' if len(err) > 20 else err
        
        line = ""
        bucket_counts = error_buckets[err]
        max_in_type = max(bucket_counts.values()) if bucket_counts else 1
        
        for bucket in display_buckets:
            cnt = bucket_counts.get(bucket, 0)
            if cnt > 0:
                # 根据密度选择显示强度
                if cnt > max_in_type * 0.7:
                    line += symbol
                elif cnt > max_in_type * 0.4:
                    line += symbol.replace('●', '○').replace('■', '□').replace('▲', '△')
                else:
                    line += '·'
            else:
                line += ' '
        
        print(f"{err_display:22s} ({count:4d}) |{line}|")
    
    # X 轴时间标签
    print(" " * 30 + "-" * width)
    if display_buckets:
        start = display_buckets[0].strftime("%H:%M")
        end = display_buckets[-1].strftime("%H:%M")
        print(" " * 30 + f"{start}" + " " * (width - len(start) - len(end)) + end)
    
    print("=" * (width + 30))
    print(f"图例: 符号密度表示事件频率，不同符号代表不同错误类型")


def detect_anomalies(dt_list, interval=timedelta(minutes=1), threshold_multiplier=3.0):
    """
    检测异常流量（突发性攻击模式）
    
    参数：
        dt_list: datetime 对象列表
        interval: 时间分桶间隔
        threshold_multiplier: 异常阈值（相对于平均值的倍数）
    """
    if not dt_list:
        return []
    
    buckets = get_time_buckets(dt_list, interval)
    bucket_counts = Counter()
    
    for dt in dt_list:
        for i, bucket_time in enumerate(buckets):
            if dt >= bucket_time and (i == len(buckets)-1 or dt < buckets[i+1]):
                bucket_counts[bucket_time] += 1
                break
    
    # 计算平均值和标准差
    counts = list(bucket_counts.values())
    avg = sum(counts) / len(counts) if counts else 0
    variance = sum((c - avg) ** 2 for c in counts) / len(counts) if counts else 0
    std_dev = math.sqrt(variance)
    
    threshold = avg + threshold_multiplier * std_dev
    
    anomalies = [(bucket, count) for bucket, count in bucket_counts.items() if count > threshold]
    anomalies.sort(key=lambda x: -x[1])
    
    if anomalies:
        print(f"\n⚠️  检测到 {len(anomalies)} 个异常流量峰值（阈值: {threshold:.1f}，均值: {avg:.1f}）")
        print("-" * 70)
        for bucket, count in anomalies[:10]:
            time_str = bucket.strftime("%Y-%m-%d %H:%M:%S")
            bar_len = int((count / max(c for _, c in anomalies)) * 40)
            bar = "█" * bar_len
            print(f"  {time_str}  ({count:4d}): {bar}")
        print("-" * 70)
    else:
        print(f"\n✅ 未检测到异常流量（阈值: {threshold:.1f}，均值: {avg:.1f}）")
    
    return anomalies


def main():
    parser = argparse.ArgumentParser(
        description="时间线错误事件ASCII可视化工具（网安版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python timeline_visualization.py events.json --mode heatmap
  python timeline_visualization.py events.json --mode wave --interval 30s
  python timeline_visualization.py events.json --mode timeline --top 8
  python timeline_visualization.py events.json --detect-anomaly
        """
    )
    
    parser.add_argument("file", help="error_events.json 文件路径")
    parser.add_argument("--mode", "-m", 
                       choices=['heatmap', 'wave', 'timeline', 'all'],
                       default='all',
                       help="可视化模式：heatmap(热力图), wave(冲击波), timeline(多错误时间线), all(全部)")
    parser.add_argument("--interval", "-i", 
                       default='5m',
                       help="时间分桶间隔，如 '1m', '5m', '30s', '1h' (默认 5m)")
    parser.add_argument("--width", "-w", type=int, default=80, help="图表宽度（字符数）")
    parser.add_argument("--height", type=int, default=20, help="图表高度（行数，仅热力图）")
    parser.add_argument("--top", "-t", type=int, default=5, help="显示前 N 种错误（仅时间线模式）")
    parser.add_argument("--detect-anomaly", "-d", action='store_true',
                       help="检测异常流量（突发性攻击）")
    parser.add_argument("--anomaly-threshold", type=float, default=3.0,
                       help="异常检测阈值倍数（默认 3.0 倍标准差）")
    
    args = parser.parse_args()
    
    # 读取 JSON 数据
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        sys.exit(1)
    
    timestamps = data.get('timestamps', [])
    events = data.get('events', [])
    prime_map = data.get('prime_map', {})
    
    if not timestamps or not events:
        print("⚠️  文件中没有时间戳或事件数据")
        sys.exit(1)
    
    # 解析时间戳
    try:
        dt_list = [datetime.fromisoformat(ts) for ts in timestamps]
    except Exception as e:
        print(f"❌ 解析时间戳失败: {e}")
        sys.exit(1)
    
    # 解析时间间隔
    try:
        interval = parse_interval(args.interval)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # 打印基础统计
    print(f"\n📁 文件: {args.file}")
    print(f"⏰ 时间范围: {min(dt_list).strftime('%Y-%m-%d %H:%M:%S')} → {max(dt_list).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 总事件数: {len(events)}")
    print(f"⏱️  时间跨度: {(max(dt_list) - min(dt_list))}")
    
    # 异常检测（如果启用）
    if args.detect_anomaly:
        detect_anomalies(dt_list, interval, args.anomaly_threshold)
    
    # 根据模式选择可视化
    if args.mode in ['heatmap', 'all']:
        print_heatmap(dt_list, interval, args.width, args.height)
    
    if args.mode in ['wave', 'all']:
        print_wave_chart(dt_list, interval, args.width, 15)
    
    if args.mode in ['timeline', 'all']:
        print_multi_timeline(events, prime_map, interval, args.width, args.top, timestamps)


if __name__ == "__main__":
    main()
