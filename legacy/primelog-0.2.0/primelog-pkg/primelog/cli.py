#!/usr/bin/env python3
"""
primelog CLI v0.2.0 — 纯参数解析层

职责：解析用户命令 → 委托给 PrimeLogOrchestrator 执行。
所有逻辑在 Orchestrator，这里只负责"听用户说什么"。
"""

import sys, os, glob, argparse


def _o():
    from primelog.core.orchestrator import _default_orchestrator
    return _default_orchestrator


# ─────────────────────────────────────────────────────────────
# 命令处理函数
# ─────────────────────────────────────────────────────────────

def cmd_scan(a):
    d = os.path.abspath(a.directory or ".")
    if not os.path.isdir(d):
        print(f"❌ 目录不存在: {d}"); sys.exit(1)
    print(f"\n✅ 共加载 {_o().scan(d)} 个组件")

def cmd_show_errors(a):
    _o().show_errors(project=a.project or "", log_dir=a.log_dir or "",
                     log_file=a.file or "", adj_file=getattr(a,'adj',"") or "")

def cmd_stats(a):
    _o().stats(project=a.project or "", log_dir=a.log_dir or "",
               log_file=a.file or "")

def cmd_histogram(a):
    _o().histogram(project=a.project or "", log_dir=a.log_dir or "",
                   log_file=a.file or "", top=a.top, width=a.width,
                   log_scale=a.log)

def cmd_timeline(a):
    _o().timeline(project=a.project or "", log_dir=a.log_dir or "",
                  log_file=a.file or "", mode=a.mode, interval=a.interval,
                  width=a.width, height=a.height, top=a.top,
                  detect_anomaly=a.detect_anomaly,
                  anomaly_threshold=a.anomaly_threshold)

def cmd_timeline_analysis(a):
    _o().timeline_analysis(project=a.project or "", log_dir=a.log_dir or "",
                            log_file=a.file or "")

def cmd_convert(a):
    _o().convert(project=a.project or "", log_dir=a.log_dir or "",
                 log_file=a.file or "", fmt=a.format, output=a.output or "",
                 index=a.index, start=a.start or "", end=a.end or "",
                 error_types=a.error_types or "", component=a.component or "")

def cmd_fft_prep(a):
    _o().fft_prep(project=a.project or "", log_dir=a.log_dir or "",
                  log_file=a.file or "", mode=a.mode,
                  bin_size=a.bin_size, output=a.output or "")

def cmd_archive(a):
    _o().archive(project=a.project or "", log_dir=a.log_dir or "",
                 keep=a.keep, compressor=a.compressor)

def cmd_export(a):
    _o().export(project=a.project or "", output_dir=a.out or "")

def cmd_loadmark(a):
    recursive = a.r or (a.L is not None)
    max_depth = a.L if a.L is not None else -1
    action = "消除" if a.x else "添加"
    scope  = f"递归深度={max_depth}" if a.L is not None \
             else ("递归" if a.r else "当前目录")
    print(f"[primelog] {action} __loadmark__  {scope}  目录: {a.directory}\n")
    _o().loadmark(directory=a.directory, remove=a.x,
                  recursive=recursive, max_depth=max_depth)

def cmd_register(a):
    files = []
    for pat in a.files:
        m = glob.glob(pat)
        files.extend(m if m else [pat])
    if not files:
        print("❌ 未找到匹配的文件"); return
    _o().register(files=files, type_=a.type,
                  project=a.project or "", signature=a.signature or "")

def cmd_version(a):
    import primelog; print(f"primelog {primelog.__version__}")


# ─────────────────────────────────────────────────────────────
# 参数定义
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='primelog',
        description='PrimeLog v0.2.0 — Decompose Anything. Understand Everything.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令速查:
  primelog register  *.py --type service --project my-proj
  primelog loadmark  -r ./my_project
  primelog scan      ./my_project
  primelog show-errors  --project my-proj
  primelog stats        --project my-proj
  primelog histogram    --project my-proj --top 20
  primelog timeline     --project my-proj --mode heatmap
  primelog convert      --project my-proj --format csv --output out.csv
  primelog fft-prep     --project my-proj --mode count
  primelog archive      --project my-proj --keep 30
  primelog export       --project my-proj --out ./logs
        """
    )
    S = parser.add_subparsers(dest='command')

    # ── scan ──────────────────────────────────────────────────
    p = S.add_parser('scan', help='扫描目录，注册所有组件')
    p.add_argument('directory', nargs='?', default='.')

    # ── show-errors ───────────────────────────────────────────
    p = S.add_parser('show-errors', help='显示错误事件详情')
    p.add_argument('file', nargs='?')
    p.add_argument('--adj')
    p.add_argument('--log-dir', default=None)
    p.add_argument('--project', default=None)

    # ── stats ─────────────────────────────────────────────────
    p = S.add_parser('stats', help='统计错误分布')
    p.add_argument('file', nargs='?')
    p.add_argument('--log-dir', default=None)
    p.add_argument('--project', default=None)

    # ── histogram ─────────────────────────────────────────────
    p = S.add_parser('histogram', help='ASCII 错误频率直方图')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)
    p.add_argument('--top',   '-t', type=int, default=15, help='显示前 N 种错误')
    p.add_argument('--width', '-w', type=int, default=60, help='直方图宽度')
    p.add_argument('--log',   action='store_true',        help='对数归一化')

    # ── timeline ──────────────────────────────────────────────
    p = S.add_parser('timeline', help='ASCII 时间线可视化（热力图/冲击波/多类型）')
    p.add_argument('file', nargs='?')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)
    p.add_argument('--mode', '-m', choices=['heatmap','wave','timeline','all'],
                   default='all')
    p.add_argument('--interval', '-i', default='1m',
                   help='时间粒度，如 30s / 5m / 1h（默认 1m）')
    p.add_argument('--width',  '-w', type=int, default=80)
    p.add_argument('--height', type=int, default=20)
    p.add_argument('--top',    '-t', type=int, default=5)
    p.add_argument('--detect-anomaly', '-d', action='store_true')
    p.add_argument('--anomaly-threshold', type=float, default=3.0)

    # ── timeline-analysis ─────────────────────────────────────
    p = S.add_parser('timeline-analysis', help='按分钟统计事件数（轻量分析）')
    p.add_argument('file', nargs='?')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)

    # ── convert ───────────────────────────────────────────────
    p = S.add_parser('convert', help='将日志导出为 CSV / JSONL / Elasticsearch 格式')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project',     default=None)
    p.add_argument('--log-dir',     default=None)
    p.add_argument('--format', '-f', choices=['csv','jsonl','elastic'], default='csv')
    p.add_argument('--output', '-o', default=None)
    p.add_argument('--index',        default='primelog')
    p.add_argument('--start',        default=None)
    p.add_argument('--end',          default=None)
    p.add_argument('--error-types',  default=None)
    p.add_argument('--component',    default=None)

    # ── fft-prep ──────────────────────────────────────────────
    p = S.add_parser('fft-prep', help='为 FFT 频域分析准备时间序列数据')
    p.add_argument('file', nargs='?')
    p.add_argument('--project',  default=None)
    p.add_argument('--log-dir',  default=None)
    p.add_argument('--mode',     choices=['interval','count'], default='interval')
    p.add_argument('--bin-size', type=float, default=1.0)
    p.add_argument('--output', '-o', default=None)

    # ── archive ───────────────────────────────────────────────
    p = S.add_parser('archive', help='归档旧日志')
    p.add_argument('--keep',       type=int, default=30)
    p.add_argument('--log-dir',    default=None)
    p.add_argument('--project',    default=None)
    p.add_argument('--compressor', choices=['7z','tar'], default='tar')

    # ── export ────────────────────────────────────────────────
    p = S.add_parser('export', help='导出当前运行日志')
    p.add_argument('--out',     default=None)
    p.add_argument('--project', default=None)

    # ── loadmark ──────────────────────────────────────────────
    p = S.add_parser('loadmark', help='管理 __loadmark__ 标记文件')
    p.add_argument('directory')
    p.add_argument('-r', action='store_true', default=False)
    p.add_argument('-L', type=int, metavar='深度', default=None)
    p.add_argument('-x', action='store_true', default=False)

    # ── register ──────────────────────────────────────────────
    p = S.add_parser('register', help='给 .py 文件打上 PrimeLog 印章')
    p.add_argument('files', nargs='+')
    p.add_argument('--type',      required=True)
    p.add_argument('--project',   required=True)
    p.add_argument('--signature', default='')

    # ── version ───────────────────────────────────────────────
    S.add_parser('version', help='显示版本')

    args = parser.parse_args()

    dispatch = {
        'scan':              cmd_scan,
        'show-errors':       cmd_show_errors,
        'stats':             cmd_stats,
        'histogram':         cmd_histogram,
        'timeline':          cmd_timeline,
        'timeline-analysis': cmd_timeline_analysis,
        'convert':           cmd_convert,
        'fft-prep':          cmd_fft_prep,
        'archive':           cmd_archive,
        'export':            cmd_export,
        'loadmark':          cmd_loadmark,
        'register':          cmd_register,
        'version':           cmd_version,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
