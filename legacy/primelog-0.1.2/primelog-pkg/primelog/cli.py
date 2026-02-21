#!/usr/bin/env python3
"""
primelog CLI

用法：
    primelog scan   [目录]          # 扫描并注册组件（默认当前目录）
    primelog show-errors [日志文件]  # 显示错误事件详情
    primelog stats   [日志文件]      # 统计错误分布
    primelog archive [--keep N天]   # 归档旧日志
    primelog export  [--out 目录]   # 导出当前运行日志
    primelog version                # 显示版本
"""

import sys
import os
import argparse


def _find_latest_log(log_dir: str, pattern: str):
    import glob
    files = glob.glob(os.path.join(log_dir, pattern))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def cmd_scan(args):
    """扫描目标目录，注册所有组件并打印组件树"""
    import primelog
    directory = args.directory or "."
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在: {directory}")
        sys.exit(1)
    n = primelog.scan(directory)
    print(f"\n✅ 共加载 {n} 个组件")


def cmd_show_errors(args):
    """显示错误事件详情"""
    log_dir = args.log_dir or os.path.join(os.getcwd(), "logs")
    if getattr(args, 'project', None):
        log_dir = os.path.join(log_dir, args.project)
    log_file = args.file or _find_latest_log(log_dir, "error_events_*.json")
    adj_file = args.adj  or _find_latest_log(log_dir, "adjacency_matrix_*.json")

    if not log_file:
        print(f"❌ 在 {log_dir} 下未找到 error_events_*.json")
        sys.exit(1)
    if not adj_file:
        print(f"❌ 在 {log_dir} 下未找到 adjacency_matrix_*.json")
        sys.exit(1)

    import json
    with open(adj_file) as f:
        nodes = json.load(f)['nodes']
    with open(log_file) as f:
        data = json.load(f)

    prime_map = data['prime_map']
    rev_map   = {v: k for k, v in prime_map.items()}
    events    = data['events']
    timestamps = data.get('timestamps', [])

    error_count = 0
    print(f"\n错误事件详情  ({log_file})\n{'─'*70}")
    for i, (t, caller, callee, composite, log_val) in enumerate(events):
        if composite == 1:
            continue
        error_count += 1
        remaining = composite
        errors = []
        for p, name in rev_map.items():
            if p > 1 and remaining % p == 0:
                errors.append(name)
                while remaining % p == 0:
                    remaining //= p
        ts = timestamps[i] if i < len(timestamps) else ""
        caller_name = nodes[caller] if caller < len(nodes) else f"#{caller}"
        callee_name = nodes[callee] if callee < len(nodes) else f"#{callee}"
        print(f"t={t:4d}  {caller_name:30s} → {callee_name:30s}")
        print(f"       errors={errors}  composite={composite}  {ts}")
    if error_count == 0:
        print("  ✅ 无错误事件")
    print(f"{'─'*70}\n共 {error_count} 个错误事件（总事件 {len(events)} 条）")


def cmd_stats(args):
    """统计错误分布"""
    log_dir  = args.log_dir or os.path.join(os.getcwd(), "logs")
    if getattr(args, 'project', None):
        log_dir = os.path.join(log_dir, args.project)
    log_file = args.file or _find_latest_log(log_dir, "error_events_*.json")
    adj_file = _find_latest_log(log_dir, "adjacency_matrix_*.json")

    if not log_file:
        print(f"❌ 在 {log_dir} 下未找到 error_events_*.json")
        sys.exit(1)

    import json
    from collections import Counter

    with open(log_file) as f:
        data = json.load(f)

    nodes     = []
    if adj_file:
        with open(adj_file) as f:
            nodes = json.load(f)['nodes']

    prime_map = data['prime_map']
    rev_map   = {v: k for k, v in prime_map.items()}
    events    = data['events']

    caller_errors = Counter()
    callee_errors = Counter()
    total_errors  = Counter()

    for t, caller, callee, composite, _ in events:
        if composite == 1:
            continue
        remaining = composite
        errors = []
        for p, name in rev_map.items():
            if p > 1 and remaining % p == 0:
                errors.append(name)
                while remaining % p == 0:
                    remaining //= p
        caller_name = nodes[caller] if caller < len(nodes) else f"#{caller}"
        callee_name = nodes[callee] if callee < len(nodes) else f"#{callee}"
        for e in errors:
            total_errors[e]          += 1
            caller_errors[(caller_name, e)] += 1
            callee_errors[(callee_name, e)] += 1

    print(f"\n错误统计  ({log_file})\n{'─'*60}")
    print(f"\n全局错误类型分布:")
    for err, cnt in total_errors.most_common():
        print(f"  {err:25s}: {cnt}")

    print(f"\n按调用者统计（Top 10）:")
    for (comp, err), cnt in caller_errors.most_common(10):
        print(f"  {comp:30s}  {err:20s}: {cnt}")

    print(f"\n按被调用者统计（Top 10）:")
    for (comp, err), cnt in callee_errors.most_common(10):
        print(f"  {comp:30s}  {err:20s}: {cnt}")


def cmd_archive(args):
    """归档旧日志（调用 log_librarian）"""
    from primelog.logs.log_librarian import main as librarian_main
    # 把 argparse 参数转换成 log_librarian 期望的格式
    sys.argv = ['log_librarian']
    if args.keep:
        sys.argv += ['--keep', str(args.keep)]
    if args.log_dir:
        sys.argv += ['--log-dir', args.log_dir]
    if args.compressor:
        sys.argv += ['--compressor', args.compressor]
    librarian_main()


def cmd_export(args):
    """导出当前运行日志"""
    import primelog
    out = args.out or os.path.join(os.getcwd(), "logs")
    proj = getattr(args, 'project', None) or ''
    primelog.export(project=proj, output_dir=out)


def cmd_register(args):
    """给 .py 文件打上 PrimeLog 印章"""
    from primelog.tools.register_file import stamp, stamp_multiple
    import glob

    # 支持通配符，如 *.py
    files = []
    for pattern in args.files:
        matched = glob.glob(pattern)
        if matched:
            files.extend(matched)
        else:
            files.append(pattern)  # 让 stamp 自己报错

    if not files:
        print("❌ 未找到匹配的文件")
        return

    sig = args.signature or ""

    if len(files) == 1:
        ok, msg = stamp(files[0], type_=args.type, project=args.project, signature=sig)
        print(msg)
    else:
        stamp_multiple(files, type_=args.type, project=args.project, signature=sig)


def cmd_version(args):
    import primelog
    print(f"primelog {primelog.__version__}")


def main():
    parser = argparse.ArgumentParser(
        prog='primelog',
        description='PrimeLog — Decompose Anything. Understand Everything.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  primelog scan ./my_project        扫描并注册组件
  primelog show-errors              显示最新日志的错误详情
  primelog stats                    统计错误分布
  primelog archive --keep 30        归档30天前的日志
  primelog export --out ./logs      导出当前运行日志
        """
    )

    sub = parser.add_subparsers(dest='command')

    # scan
    p_scan = sub.add_parser('scan', help='扫描目标目录，注册所有组件')
    p_scan.add_argument('directory', nargs='?', default='.', help='目标目录（默认：当前目录）')

    # show-errors
    p_err = sub.add_parser('show-errors', help='显示错误事件详情')
    p_err.add_argument('file',    nargs='?', help='error_events_*.json 路径（默认：最新）')
    p_err.add_argument('--adj',   help='adjacency_matrix_*.json 路径')
    p_err.add_argument('--log-dir', default=None, help='日志目录（默认：./logs）')
    p_err.add_argument('--project', default=None, help='项目名，自动定位到 <log-dir>/<project>/')

    # stats
    p_stats = sub.add_parser('stats', help='统计错误分布')
    p_stats.add_argument('file',      nargs='?', help='error_events_*.json 路径（默认：最新）')
    p_stats.add_argument('--log-dir', default=None, help='日志目录（默认：./logs）')
    p_stats.add_argument('--project', default=None, help='项目名，自动定位到 <log-dir>/<project>/')

    # archive
    p_arc = sub.add_parser('archive', help='归档旧日志')
    p_arc.add_argument('--keep',       type=int, default=30, help='保留最近 N 天（默认30）')
    p_arc.add_argument('--log-dir',    default=None)
    p_arc.add_argument('--project',    default=None, help='只归档指定项目的日志')
    p_arc.add_argument('--compressor', choices=['7z','tar'], default='tar')

    # export
    p_exp = sub.add_parser('export', help='导出当前运行日志')
    p_exp.add_argument('--out',     default=None, help='输出目录（默认：./logs）')
    p_exp.add_argument('--project', default=None, help='项目名，写到 <out>/<project>/')

    # register
    p_reg = sub.add_parser('register', help='给 .py 文件打上 PrimeLog 印章')
    p_reg.add_argument('files',     nargs='+',  help='.py 文件路径（支持通配符 *.py）')
    p_reg.add_argument('--type',    required=True, help='组件类型，如 service / algorithm / tool')
    p_reg.add_argument('--project', required=True, help='项目名，如 pocket-optimizer')
    p_reg.add_argument('--signature', default='',  help='方法签名，如 "run() -> None"')

    # version
    sub.add_parser('version', help='显示版本')

    args = parser.parse_args()

    dispatch = {
        'scan':        cmd_scan,
        'show-errors': cmd_show_errors,
        'stats':       cmd_stats,
        'archive':     cmd_archive,
        'export':      cmd_export,
        'version':     cmd_version,
        'register':    cmd_register,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
