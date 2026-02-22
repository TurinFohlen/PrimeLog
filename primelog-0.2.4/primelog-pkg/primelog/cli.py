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
                 error_types=a.error_types or "", component=a.component or "",
                 raw=getattr(a, 'raw', False))

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
        description='PrimeLog — 基于素数唯一分解定理的组件日志与可观测性框架',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
PrimeLog 将组件调用关系与错误事件编码为数学结构，支持事后深度分析。
核心命令分类:

🛠️ 初始化与接入
  register    自动为 .py 文件添加 @primelog.component 装饰器
  loadmark    管理 __loadmark__ 标记，告诉加载器扫描哪些目录
  scan        扫描并加载所有带标记的组件

📊 实时日志导出
  export      导出当前运行日志（JSON + Wolfram 格式）

🔍 日志分析（基于已导出的文件）
  show-errors     显示错误事件详情
  stats           统计错误分布
  histogram       ASCII 错误频率直方图
  timeline        时间线可视化（热力图/冲击波/多类型）
  timeline-analysis 按分钟统计事件数
  convert         导出为 CSV / JSONL / Elasticsearch 格式
  fft-prep        为 FFT 频域分析准备时间序列数据

🗂️ 维护
  archive     归档旧日志

其他:
  version     显示版本号

使用示例:
  primelog register  *.py --type service --project my-proj
  primelog loadmark  -r ./my_project
  primelog scan      ./my_project
  primelog export    --project my-proj
  primelog show-errors  --project my-proj
  primelog convert     --project my-proj --format csv --raw
  primelog archive     --project my-proj --keep 30

更多帮助: primelog <command> -h
        """
    )
    S = parser.add_subparsers(dest='command')

    # ── scan ──────────────────────────────────────────────────
    p = S.add_parser('scan', help='扫描目录，注册所有组件')
    p.add_argument('directory', nargs='?', default='.',
                   help='要扫描的根目录（默认当前目录）')

    # ── show-errors ───────────────────────────────────────────
    p = S.add_parser('show-errors', help='显示错误事件详情')
    p.add_argument('file', nargs='?', help='指定 error_events_*.json 文件（默认最新）')
    p.add_argument('--adj', help='指定 adjacency_matrix_*.json 文件（默认自动查找）')
    p.add_argument('--log-dir', default=None, help='日志根目录（默认 ./logs）')
    p.add_argument('--project', default=None, help='项目名（与 --log-dir 一起定位日志）')

    # ── stats ─────────────────────────────────────────────────
    p = S.add_parser('stats', help='统计错误分布（按类型、调用者、被调用者）')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--log-dir', default=None, help='日志根目录')
    p.add_argument('--project', default=None, help='项目名')

    # ── histogram ─────────────────────────────────────────────
    p = S.add_parser('histogram', help='ASCII 错误频率直方图')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project', default=None, help='项目名')
    p.add_argument('--log-dir', default=None, help='日志根目录')
    p.add_argument('--top',   '-t', type=int, default=15, help='显示前 N 种错误（默认 15）')
    p.add_argument('--width', '-w', type=int, default=60, help='直方图宽度（默认 60）')
    p.add_argument('--log',   action='store_true',        help='使用对数归一化')

    # ── timeline ──────────────────────────────────────────────
    p = S.add_parser('timeline', help='ASCII 时间线可视化（热力图/冲击波/多类型）')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project', default=None, help='项目名')
    p.add_argument('--log-dir', default=None, help='日志根目录')
    p.add_argument('--mode', '-m', choices=['heatmap','wave','timeline','all'],
                   default='all', help='可视化模式：heatmap(热力图) / wave(冲击波) / timeline(多类型) / all(全部)')
    p.add_argument('--interval', '-i', default='1m',
                   help='时间粒度，如 30s / 5m / 1h（默认 1m）')
    p.add_argument('--width',  '-w', type=int, default=80, help='输出宽度（默认 80）')
    p.add_argument('--height', type=int, default=20, help='输出高度（默认 20）')
    p.add_argument('--top',    '-t', type=int, default=5, help='显示前 N 种错误类型（默认 5）')
    p.add_argument('--detect-anomaly', '-d', action='store_true', help='启用异常检测')
    p.add_argument('--anomaly-threshold', type=float, default=3.0,
                   help='异常阈值（标准差倍数，默认 3.0）')

    # ── timeline-analysis ─────────────────────────────────────
    p = S.add_parser('timeline-analysis', help='按分钟统计事件数（轻量分析）')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project', default=None, help='项目名')
    p.add_argument('--log-dir', default=None, help='日志根目录')

    # ── convert ───────────────────────────────────────────────
    p = S.add_parser('convert', help='将日志导出为 CSV / JSONL / Elasticsearch 格式')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project',     default=None, help='项目名')
    p.add_argument('--log-dir',     default=None, help='日志根目录')
    p.add_argument('--format', '-f', choices=['csv','jsonl','elastic'], default='csv',
                   help='导出格式（默认 csv）')
    p.add_argument('--output', '-o', default=None, help='输出文件路径（自动生成若未指定）')
    p.add_argument('--index',        default='primelog', help='Elasticsearch 索引名（默认 primelog）')
    p.add_argument('--start',        default=None, help='起始时间（ISO 格式，如 2026-02-20T00:00:00）')
    p.add_argument('--end',          default=None, help='结束时间（ISO 格式）')
    p.add_argument('--error-types',  default=None, help='只导出指定错误类型，逗号分隔')
    p.add_argument('--component',    default=None, help='只导出涉及该组件的事件（调用者或被调用者）')
    p.add_argument('--raw', action='store_true', help='不解码错误，直接输出原始 log_value（适合数学分析）')

    # ── fft-prep ──────────────────────────────────────────────
    p = S.add_parser('fft-prep', help='为 FFT 频域分析准备时间序列数据')
    p.add_argument('file', nargs='?', help='error_events_*.json（默认最新）')
    p.add_argument('--project',  default=None, help='项目名')
    p.add_argument('--log-dir',  default=None, help='日志根目录')
    p.add_argument('--mode',     choices=['interval','count'], default='interval',
                   help='输出模式：interval(固定时间间隔) / count(按事件序号)')
    p.add_argument('--bin-size', type=float, default=1.0, help='时间窗口大小（秒，默认 1.0）')
    p.add_argument('--output', '-o', default=None, help='输出文件路径（默认自动生成）')

    # ── archive ───────────────────────────────────────────────
    p = S.add_parser('archive', help='归档旧日志（压缩超过 keep 天的文件）')
    p.add_argument('--keep',       type=int, default=30, help='保留最近 N 天（默认 30）')
    p.add_argument('--log-dir',    default=None, help='日志根目录（默认 ./logs）')
    p.add_argument('--project',    default=None, help='项目名（如不指定则归档所有项目）')
    p.add_argument('--compressor', choices=['7z','tar'], default='tar',
                   help='压缩工具：tar 或 7z（需安装 p7zip）')

    # ── export ────────────────────────────────────────────────
    p = S.add_parser('export', help='导出当前运行日志（JSON + WL 文件）')
    p.add_argument('--out',     default=None, help='输出根目录（默认 ./logs）')
    p.add_argument('--project', default=None, help='项目名（默认使用 init 时设置的项目）')

    # ── loadmark ──────────────────────────────────────────────
    p = S.add_parser('loadmark', help='管理 __loadmark__ 标记文件')
    p.add_argument('directory', help='要操作的目录')
    p.add_argument('-r', action='store_true', default=False,
                   help='递归处理所有子目录')
    p.add_argument('-L', type=int, metavar='深度', default=None,
                   help='递归深度限制（如 -L 2）')
    p.add_argument('-x', action='store_true', default=False,
                   help='消除标记（默认是添加）')

    # ── register ──────────────────────────────────────────────
    p = S.add_parser('register', help='给 .py 文件打上 PrimeLog 印章')
    p.add_argument('files', nargs='+', help='要处理的 .py 文件（支持通配符 *.py）')
    p.add_argument('--type',      required=True, help='组件类型，如 service/algorithm/tool')
    p.add_argument('--project',   required=True, help='项目名，用作组件名前缀')
    p.add_argument('--signature', default='', help='方法签名说明（可选）')

    # ── version ───────────────────────────────────────────────
    S.add_parser('version', help='显示版本号')

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