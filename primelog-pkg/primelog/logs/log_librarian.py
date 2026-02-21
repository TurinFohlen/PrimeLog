#!/usr/bin/env python3
"""
log_librarian.py - 日志文件管理工具（支持7z高压缩，支持守护模式）
用法：
    python log_librarian.py [选项]

一次性模式：
    python log_librarian.py --keep 30

守护模式（每小时执行）：
    python log_librarian.py --daemon --interval 3600 --keep 30
"""

import os
import sys
import glob
import re
import shutil
import argparse
import subprocess
import time
import signal
import atexit
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------- 配置和全局变量 ----------------------------
running = True
pid_file = None

def signal_handler(sig, frame):
    global running
    print("\n收到退出信号，正在停止...")
    running = False

def cleanup():
    if pid_file and os.path.exists(pid_file):
        os.remove(pid_file)

# ---------------------------- 日期解析和文件筛选 ----------------------------
def parse_date_from_filename(filename):
    """从文件名中提取日期对象，支持常见格式"""
    base = os.path.basename(filename)
    patterns = [
        (r'(\d{8})', '%Y%m%d'),                     # 20260219
        (r'(\d{8}_\d{6})', '%Y%m%d_%H%M%S'),        # 20260219_123456
        (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),       # 2026-02-19
        (r'(\d{4}\d{2}\d{2}T\d{6})', '%Y%m%dT%H%M%S') # 20260219T123456
    ]
    for pat, fmt in patterns:
        m = re.search(pat, base)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                continue
    return None

def get_files_by_date(log_dir, cutoff_date):
    """获取截止日期之前的所有日志文件（error_events_* 和 adjacency_matrix_*）"""
    files = []
    for pattern in ["error_events_*.json", "adjacency_matrix_*.json", "*.wl"]:
        files.extend(glob.glob(os.path.join(log_dir, pattern)))
    # 筛选出日期早于 cutoff_date 且可解析日期的文件
    old_files = []
    for f in files:
        dt = parse_date_from_filename(f)
        if dt and dt < cutoff_date:
            old_files.append((f, dt))
    # 按日期排序
    old_files.sort(key=lambda x: x[1])
    return old_files

def group_files_by_period(file_list, period='month'):
    """将文件按时间段分组"""
    groups = {}
    for f, dt in file_list:
        if period == 'month':
            key = dt.strftime("%Y-%m")
        elif period == 'week':
            # 按周一所在年份和周数分组
            year, week, _ = dt.isocalendar()
            key = f"{year}-W{week:02d}"
        elif period == 'day':
            key = dt.strftime("%Y-%m-%d")
        else:
            raise ValueError("period 必须是 month/week/day")
        groups.setdefault(key, []).append((f, dt))
    return groups

# ---------------------------- 压缩函数 ----------------------------
def compress_7z(file_list, archive_path, dry_run=False):
    """使用 7z 压缩文件列表"""
    if not file_list:
        return
    file_paths = [f for f, _ in file_list]
    cmd = ["7z", "a", "-t7z", "-mx=9", archive_path] + file_paths
    print(f"执行: {' '.join(cmd)}")
    if not dry_run:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"✅ 已创建: {archive_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ 压缩失败: {e.stderr.decode() if e.stderr else '未知错误'}")
            return False
        except FileNotFoundError:
            print("❌ 未找到 7z 命令，请安装 p7zip")
            return False
    return True

def compress_tar(file_list, archive_path, dry_run=False):
    """使用 tar/gzip 压缩文件列表"""
    if not file_list:
        return
    import tarfile
    file_paths = [f for f, _ in file_list]
    print(f"打包为: {archive_path}")
    if not dry_run:
        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for f in file_paths:
                    tar.add(f, arcname=os.path.basename(f))
            print(f"✅ 已创建: {archive_path}")
        except Exception as e:
            print(f"❌ 压缩失败: {e}")
            return False
    return True

# ---------------------------- 核心处理函数 ----------------------------
def run_once(args, log_dir, archive_dir, cutoff):
    """执行一次归档操作"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始归档检查")
    old_files = get_files_by_date(log_dir, cutoff)
    if not old_files:
        print("✅ 没有需要归档的文件。")
        return True

    print(f"🔍 找到 {len(old_files)} 个待归档文件")
    groups = group_files_by_period(old_files, args.group_by)
    print(f"📊 将按 {args.group_by} 分组，共 {len(groups)} 组")

    total_archived = 0
    for period, file_list in groups.items():
        ext = "7z" if args.compressor == '7z' else "tar.gz"
        archive_name = f"logs_{period}.{ext}"
        archive_path = os.path.join(archive_dir, archive_name)

        # 避免重名
        base, ext = os.path.splitext(archive_path)
        counter = 1
        while os.path.exists(archive_path):
            archive_path = f"{base}_{counter}{ext}"
            counter += 1

        print(f"\n📦 组 {period}: {len(file_list)} 个文件 -> {os.path.basename(archive_path)}")
        if args.dry_run:
            continue

        if args.compressor == '7z':
            ok = compress_7z(file_list, archive_path, dry_run=False)
        else:
            ok = compress_tar(file_list, archive_path, dry_run=False)

        if ok:
            total_archived += len(file_list)
            for f, _ in file_list:
                try:
                    os.remove(f)
                    print(f"    已删除: {os.path.basename(f)}")
                except Exception as e:
                    print(f"    删除失败 {os.path.basename(f)}: {e}")

    if not args.dry_run and total_archived > 0:
        print(f"\n✅ 本次归档完成，共处理 {total_archived} 个文件")
    return True

# ---------------------------- 主函数 ----------------------------
def main():
    global running, pid_file
    parser = argparse.ArgumentParser(
        description="日志文件管理工具（支持7z高压缩，支持守护模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--log-dir", default=None, help="日志目录（默认：../logs）")
    parser.add_argument("--project", default=None, help="只归档指定项目子目录，留空则归档所有项目")
    parser.add_argument("--archive-dir", default=None, help="归档目录（默认：<log-dir>/archive）")
    parser.add_argument("--group-by", choices=['month', 'week', 'day'], default='month',
                        help="按时间分组（默认：month）")
    parser.add_argument("--keep", type=int, default=30, help="保留最近 N 天（默认：30）")
    parser.add_argument("--before", help="归档指定日期之前的文件（格式：YYYY-MM-DD），优先级高于 --keep")
    parser.add_argument("--compressor", choices=['7z', 'tar'], default='7z',
                        help="压缩工具（默认：7z，需要安装 p7zip）")
    parser.add_argument("--dry-run", action='store_true', help="仅预览，不实际执行")
    parser.add_argument("--force", action='store_true', help="跳过删除确认（已自动）")

    # 守护模式参数
    parser.add_argument("--daemon", action='store_true', help="以守护模式运行，定期执行")
    parser.add_argument("--interval", type=int, default=3600,
                        help="守护模式下的循环间隔（秒，默认3600）")
    parser.add_argument("--pidfile", help="PID 文件路径（防止重复运行）")

    args = parser.parse_args()

    # ---------------------- 路径处理 ----------------------
    if args.log_dir:
        log_dir = os.path.abspath(args.log_dir)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.abspath(os.path.join(script_dir, "..", "logs"))

    if not os.path.isdir(log_dir):
        print(f"❌ 日志目录不存在: {log_dir}")
        sys.exit(1)

    if args.archive_dir:
        archive_dir = os.path.abspath(args.archive_dir)
    else:
        archive_dir = os.path.join(log_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # ---------------------- 日期截止 ----------------------
    if args.before:
        try:
            cutoff = datetime.strptime(args.before, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式错误，应为 YYYY-MM-DD")
            sys.exit(1)
    else:
        cutoff = datetime.now() - timedelta(days=args.keep)

    # 如果指定了项目，只处理该项目的子目录
    if args.project:
        log_dir     = os.path.join(log_dir, args.project)
        archive_dir = os.path.join(archive_dir, args.project)
        if not os.path.isdir(log_dir):
            print(f"❌ 项目日志目录不存在: {log_dir}")
            sys.exit(1)
        os.makedirs(archive_dir, exist_ok=True)
        print(f"🎯 只归档项目: {args.project}")

    print(f"📁 日志目录: {log_dir}")
    print(f"📦 归档目录: {archive_dir}")
    print(f"✂️  截止日期: {cutoff.strftime('%Y-%m-%d')} (保留最近 {args.keep} 天)")

    # ---------------------- 守护模式 ----------------------
    if args.daemon:
        # PID 文件处理
        if args.pidfile:
            pid_file = args.pidfile
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    old_pid = f.read().strip()
                print(f"⚠️ PID 文件 {pid_file} 已存在，可能已有实例运行 (PID: {old_pid})")
                sys.exit(1)
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
            atexit.register(cleanup)

        # 注册信号处理
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        print(f"\n🚀 进入守护模式，每 {args.interval} 秒执行一次")
        while running:
            run_once(args, log_dir, archive_dir, cutoff)
            if not running:
                break
            print(f"💤 等待 {args.interval} 秒...")
            # 使用分片睡眠以便及时响应退出信号
            for _ in range(args.interval):
                if not running:
                    break
                time.sleep(1)
        print("👋 守护进程退出")
    else:
        # 一次性模式
        run_once(args, log_dir, archive_dir, cutoff)

if __name__ == "__main__":
    main()