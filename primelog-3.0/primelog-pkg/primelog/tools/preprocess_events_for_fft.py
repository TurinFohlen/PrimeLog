#!/usr/bin/env python3
"""
preprocess_events_for_fft.py - 从错误日志提取时间戳并生成数值序列
用法:
  python preprocess_events_for_fft.py <error_events.json> [--mode interval|count] [--bin-size seconds]
"""
import json
import sys
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="为 FFT 分析准备时间序列数据")
    parser.add_argument("file", help="error_events.json 文件路径")
    parser.add_argument("--mode", choices=["interval", "count"], default="interval",
                        help="interval: 事件间隔（毫秒）；count: 每 bin 内事件数（默认 interval）")
    parser.add_argument("--bin-size", type=float, default=1.0,
                        help="count 模式下的时间窗口大小（秒，默认 1.0）")
    parser.add_argument("--output", "-o", help="输出文件名（默认打印到 stdout）")
    args = parser.parse_args()

    with open(args.file) as f:
        data = json.load(f)

    timestamps = data.get("timestamps", [])
    if not timestamps:
        print("错误：没有时间戳数据", file=sys.stderr)
        sys.exit(1)

    # 转换为 datetime 对象
    dts = [datetime.fromisoformat(ts) for ts in timestamps]
    dts.sort()  # 确保有序

    if args.mode == "interval":
        # 计算相邻事件的时间间隔（毫秒）
        intervals = []
        for i in range(1, len(dts)):
            delta_ms = (dts[i] - dts[i-1]).total_seconds() * 1000
            intervals.append(delta_ms)
        values = intervals
        print(f"生成 {len(values)} 个间隔（毫秒）", file=sys.stderr)
    else:
        # 按时间窗口计数
        start_time = dts[0]
        end_time = dts[-1]
        total_seconds = (end_time - start_time).total_seconds()
        num_bins = int(total_seconds / args.bin_size) + 1
        counts = [0] * num_bins
        for dt in dts:
            bin_idx = int((dt - start_time).total_seconds() / args.bin_size)
            counts[bin_idx] += 1
        values = counts
        print(f"生成 {len(values)} 个计数（每 {args.bin_size} 秒）", file=sys.stderr)

    # 输出
    out_fh = open(args.output, 'w') if args.output else sys.stdout
    for v in values:
        print(f"{v:.3f}" if isinstance(v, float) else v, file=out_fh)
    if args.output:
        out_fh.close()

if __name__ == "__main__":
    main()

def run(log_file: str, mode: str = "interval",
        bin_size: float = 1.0, output: str = "") -> None:
    """Orchestrator 可编程调用入口"""
    import sys as _sys
    old_argv = _sys.argv
    _sys.argv = ['preprocess_events_for_fft', log_file,
                 '--mode', mode, '--bin-size', str(bin_size)]
    if output:
        _sys.argv += ['--output', output]
    try:
        main()
    finally:
        _sys.argv = old_argv


def run(log_file: str, mode: str = "interval",
        bin_size: float = 1.0, output: str = "") -> None:
    """Orchestrator 调用入口。"""
    import sys as _sys
    argv = ['fft_prep', log_file, '--mode', mode, '--bin-size', str(bin_size)]
    if output:
        argv += ['--output', output]
    _sys.argv = argv
    main()
