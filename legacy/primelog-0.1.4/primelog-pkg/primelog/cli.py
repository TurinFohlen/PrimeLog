#!/usr/bin/env python3
"""
primelog CLI — 纯参数解析层

职责：解析用户命令 → 委托给 PrimeLogOrchestrator 执行。
逻辑全在 Orchestrator 里，这里只负责"听用户说什么"。
"""

import sys
import os
import glob
import argparse


def _get_orch():
    """懒加载默认 Orchestrator"""
    from primelog.core.orchestrator import _default_orchestrator
    return _default_orchestrator


def cmd_scan(args):
    orch = _get_orch()
    directory = os.path.abspath(args.directory or ".")
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在: {directory}")
        sys.exit(1)
    n = orch.scan(directory)
    print(f"\n✅ 共加载 {n} 个组件")


def cmd_show_errors(args):
    _get_orch().show_errors(
        project  = args.project  or "",
        log_dir  = args.log_dir  or "",
        log_file = args.file     or "",
        adj_file = getattr(args, 'adj', "") or "",
    )


def cmd_stats(args):
    _get_orch().stats(
        project  = args.project  or "",
        log_dir  = args.log_dir  or "",
        log_file = args.file     or "",
    )


def cmd_archive(args):
    _get_orch().archive(
        project    = args.project    or "",
        log_dir    = args.log_dir    or "",
        keep       = args.keep,
        compressor = args.compressor,
    )


def cmd_export(args):
    _get_orch().export(
        project    = args.project or "",
        output_dir = args.out     or "./logs",
    )


def cmd_loadmark(args):
    recursive = args.r or (args.L is not None)
    max_depth = args.L if args.L is not None else -1
    action = "消除" if args.x else "添加"
    scope  = f"递归深度={max_depth}" if args.L is not None \
             else ("递归" if args.r else "当前目录")
    print(f"[primelog] {action} __loadmark__  {scope}  目录: {args.directory}")
    print()
    _get_orch().loadmark(
        directory = args.directory,
        remove    = args.x,
        recursive = recursive,
        max_depth = max_depth,
    )


def cmd_register(args):
    files = []
    for pattern in args.files:
        matched = glob.glob(pattern)
        files.extend(matched if matched else [pattern])
    if not files:
        print("❌ 未找到匹配的文件")
        return
    _get_orch().register(
        files     = files,
        type_     = args.type,
        project   = args.project or "",
        signature = args.signature or "",
    )


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
  primelog scan ./my_project                   扫描并注册组件
  primelog register *.py --type service --project my-project
  primelog loadmark -r ./my_project            递归添加标记
  primelog show-errors --project my-project    查看错误详情
  primelog stats       --project my-project    统计分布
  primelog archive     --project my-project --keep 30
  primelog export      --project my-project --out ./logs
        """
    )

    sub = parser.add_subparsers(dest='command')

    # scan
    p = sub.add_parser('scan', help='扫描目录，注册所有组件')
    p.add_argument('directory', nargs='?', default='.', help='目标目录（默认：当前目录）')

    # show-errors
    p = sub.add_parser('show-errors', help='显示错误事件详情')
    p.add_argument('file',      nargs='?', help='error_events_*.json（默认：最新）')
    p.add_argument('--adj',     help='adjacency_matrix_*.json 路径')
    p.add_argument('--log-dir', default=None)
    p.add_argument('--project', default=None, help='项目名 → <log-dir>/<project>/')

    # stats
    p = sub.add_parser('stats', help='统计错误分布')
    p.add_argument('file',      nargs='?', help='error_events_*.json（默认：最新）')
    p.add_argument('--log-dir', default=None)
    p.add_argument('--project', default=None)

    # archive
    p = sub.add_parser('archive', help='归档旧日志')
    p.add_argument('--keep',       type=int, default=30)
    p.add_argument('--log-dir',    default=None)
    p.add_argument('--project',    default=None)
    p.add_argument('--compressor', choices=['7z', 'tar'], default='tar')

    # export
    p = sub.add_parser('export', help='导出当前运行日志')
    p.add_argument('--out',     default=None)
    p.add_argument('--project', default=None)

    # loadmark
    p = sub.add_parser('loadmark', help='管理 __loadmark__ 标记文件')
    p.add_argument('directory')
    p.add_argument('-r', action='store_true', default=False, help='递归')
    p.add_argument('-L', type=int, metavar='深度', default=None, help='递归限深度')
    p.add_argument('-x', action='store_true', default=False, help='消除标记')

    # register
    p = sub.add_parser('register', help='给 .py 文件打上 PrimeLog 印章')
    p.add_argument('files',       nargs='+', help='.py 文件路径（支持 *.py）')
    p.add_argument('--type',      required=True)
    p.add_argument('--project',   required=True)
    p.add_argument('--signature', default='')

    # version
    sub.add_parser('version', help='显示版本')

    args = parser.parse_args()

    dispatch = {
        'scan':        cmd_scan,
        'show-errors': cmd_show_errors,
        'stats':       cmd_stats,
        'archive':     cmd_archive,
        'export':      cmd_export,
        'loadmark':    cmd_loadmark,
        'register':    cmd_register,
        'version':     cmd_version,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
