#!/usr/bin/env python3
"""
primelog CLI v0.3.0 — 纯参数解析层

职责：解析用户命令 → 委托给 PrimeLogOrchestrator / 工具模块 执行。
所有逻辑在 Orchestrator 和 tools/，这里只负责"听用户说什么"。

v0.3 新增
─────────
  schema define/record/export/list/save/load  — 要素表 Schema API
  aggregate                                   — 多节点日志合并
"""

import sys, os, glob, argparse


def _o():
    from primelog.core.orchestrator import _default_orchestrator
    return _default_orchestrator


def _sr():
    from primelog.core.schema_registry import _schema_registry
    return _schema_registry


# ─────────────────────────────────────────────────────────────
#  原有命令（保持不变）
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
    import primelog
    print(f"primelog {primelog.__version__}")


# ─────────────────────────────────────────────────────────────
#  v0.3：schema 命令组
# ─────────────────────────────────────────────────────────────

def cmd_schema_define(a):
    import json
    states = {}
    if a.states:
        try:
            states = json.loads(a.states)
        except json.JSONDecodeError:
            try:
                for part in a.states.split(","):
                    k, v = part.strip().split("=")
                    states[k.strip()] = int(v.strip())
            except Exception:
                print("❌ --states 格式错误")
                print("   JSON: '{\"low\":2,\"high\":5}'")
                print("   键值: low=2,high=5")
                sys.exit(1)
    dims   = [d.strip() for d in a.dims.split(",")] if a.dims else []
    schema = _sr().define(name=a.name, states=states or None,
                          dimensions=dims, description=a.desc or "")
    print(f"✅ Schema '{a.name}' 注册")
    print(f"   states: {schema.states}")
    if dims:   print(f"   dims:   {dims}")
    if a.desc: print(f"   desc:   {a.desc}")


def cmd_schema_record(a):
    states_list = [s.strip() for s in a.states.split(",")]
    _sr().record_state(
        schema_name = a.schema,
        subject     = a.subject,
        states      = states_list,
        observer    = a.observer or "",
        project     = a.project or "__global__",
        export_dir  = a.out or ".",
    )
    print(f"✅ 记录  schema={a.schema}  subject={a.subject}  states={states_list}")


def cmd_schema_export(a):
    proj = a.project or "__global__"
    if a.schema == "__all__":
        paths = _sr().export_all_schemas(project=proj, output_dir=a.out or ".")
        if not paths:
            print("⚠️  无可导出的 Schema 事件")
        else:
            for p in paths: print(f"✅ {p}")
    else:
        path = _sr().export_schema(a.schema, project=proj,
                                   filepath=a.file or None)
        print(f"✅ {path}" if path else f"⚠️  Schema '{a.schema}' 没有事件记录")


def cmd_schema_list(a):
    schemas = _sr().list_schemas()
    if not schemas:
        print("（尚未注册任何 Schema）"); return
    for name in schemas:
        s = _sr().get(name)
        states_str = "  ".join(
            f"{k}={v}" for k, v in sorted(s.states.items(), key=lambda x: x[1]))
        print(f"  {name}")
        if s.description: print(f"    {s.description}")
        if s.dimensions:  print(f"    维度: {', '.join(s.dimensions)}")
        print(f"    状态: {states_str}")


def cmd_schema_save(a):
    _sr().save_schema_file(a.schema, a.file)
    print(f"✅ Schema '{a.schema}' → {a.file}")


def cmd_schema_load(a):
    schema = _sr().load_schema_file(a.file)
    print(f"✅ 加载 Schema '{schema.name}'（{len(schema.states)} 个状态）")


# ─────────────────────────────────────────────────────────────
#  v0.3：aggregate 命令
# ─────────────────────────────────────────────────────────────

def cmd_aggregate(a):
    from primelog.tools.aggregate import (
        discover_nodes, NodeData, aggregate, write_output
    )
    from pathlib import Path

    raw_nodes = []

    if a.dir:
        root = Path(a.dir)
        if not root.is_dir():
            print(f"❌ 不是目录: {root}"); sys.exit(1)
        discovered = discover_nodes(root)
        if not discovered:
            print(f"❌ 在 {root} 中未找到日志文件对"); sys.exit(1)
        if len(discovered) == 1 and a.node_ip:
            discovered[0] = (a.node_ip, discovered[0][1], discovered[0][2])
        raw_nodes.extend(discovered)

    if a.node:
        for node_id, ev_str, adj_str in a.node:
            ev_p, adj_p = Path(ev_str), Path(adj_str)
            if not ev_p.exists(): print(f"❌ 找不到: {ev_p}"); sys.exit(1)
            if not adj_p.exists(): print(f"❌ 找不到: {adj_p}"); sys.exit(1)
            raw_nodes.append((node_id, ev_p, adj_p))

    if not raw_nodes:
        print("❌ 请指定 --dir 或至少一个 --node"); sys.exit(1)

    print(f"[aggregate] {len(raw_nodes)} 个节点：")
    for nid, ep, ap in raw_nodes:
        print(f"  [{nid}]  {ep.name}  +  {ap.name}")

    if a.dry_run:
        print("[aggregate] --dry-run，退出"); return

    node_data = []
    for nid, ep, ap in raw_nodes:
        try:
            nd = NodeData(nid, ep, ap)
            node_data.append(nd)
            print(f"  [{nid}] {len(nd.events)} 事件  {len(nd.nodes)} 组件")
        except Exception as e:
            print(f"❌ 加载 {nid} 失败: {e}"); sys.exit(1)

    ev_g, adj_g = aggregate(node_data, global_name=a.global_name)
    ev_path, adj_path = write_output(ev_g, adj_g, Path(a.out or "."), a.global_name)

    print(f"✅ {adj_g['metadata']['n_components']} 组件  "
          f"{ev_g['metadata']['n_events']} 事件")
    print(f"   {ev_path}")
    print(f"   {adj_path}")


# ─────────────────────────────────────────────────────────────
#  参数定义
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='primelog',
        description='PrimeLog v0.3.0 — Decompose Anything. Understand Everything.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
命令速查
──────────────────────────────────────────────────────────
  # 组件注册
  primelog register  *.py --type service --project my-proj
  primelog loadmark  -r ./my_project
  primelog scan      ./my_project

  # 错误日志分析
  primelog show-errors       --project my-proj
  primelog stats             --project my-proj
  primelog histogram         --project my-proj --top 20
  primelog timeline          --project my-proj --mode heatmap
  primelog timeline-analysis --project my-proj
  primelog convert           --project my-proj --format csv -o out.csv
  primelog fft-prep          --project my-proj --mode count
  primelog export            --project my-proj --out ./logs
  primelog archive           --project my-proj --keep 30

  # 要素表 Schema（v0.3 新增）
  primelog schema define  cpu_load --states '{"low":2,"high":5}' --dims server_id
  primelog schema record  cpu_load --subject web-01 --states high
  primelog schema export  cpu_load --project my-proj
  primelog schema export  __all__  --project my-proj --out ./logs
  primelog schema list
  primelog schema save    cpu_load schemas/cpu_load.json
  primelog schema load    schemas/cpu_load.json

  # 多节点聚合（v0.3 新增）
  primelog aggregate --dir /mnt/incoming --global-name nightly -o ./global
  primelog aggregate \\
      --node 10.0.0.1 ev1.json adj1.json \\
      --node 10.0.0.2 ev2.json adj2.json -o ./global
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
    p.add_argument('file', nargs='?')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)
    p.add_argument('--top',   '-t', type=int, default=15)
    p.add_argument('--width', '-w', type=int, default=60)
    p.add_argument('--log', action='store_true', help='对数归一化')

    # ── timeline ──────────────────────────────────────────────
    p = S.add_parser('timeline', help='ASCII 时间线可视化')
    p.add_argument('file', nargs='?')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)
    p.add_argument('--mode', '-m',
                   choices=['heatmap','wave','timeline','all'], default='all')
    p.add_argument('--interval', '-i', default='1m')
    p.add_argument('--width',  '-w', type=int, default=80)
    p.add_argument('--height', type=int, default=20)
    p.add_argument('--top',    '-t', type=int, default=5)
    p.add_argument('--detect-anomaly', '-d', action='store_true')
    p.add_argument('--anomaly-threshold', type=float, default=3.0)

    # ── timeline-analysis ─────────────────────────────────────
    p = S.add_parser('timeline-analysis', help='按分钟统计事件数')
    p.add_argument('file', nargs='?')
    p.add_argument('--project', default=None)
    p.add_argument('--log-dir', default=None)

    # ── convert ───────────────────────────────────────────────
    p = S.add_parser('convert', help='导出为 CSV / JSONL / Elasticsearch 格式')
    p.add_argument('file', nargs='?')
    p.add_argument('--project',    default=None)
    p.add_argument('--log-dir',    default=None)
    p.add_argument('--format', '-f',
                   choices=['csv','jsonl','elastic'], default='csv')
    p.add_argument('--output', '-o', default=None)
    p.add_argument('--index',       default='primelog')
    p.add_argument('--start',       default=None)
    p.add_argument('--end',         default=None)
    p.add_argument('--error-types', default=None)
    p.add_argument('--component',   default=None)

    # ── fft-prep ──────────────────────────────────────────────
    p = S.add_parser('fft-prep', help='为 FFT 频域分析准备时间序列')
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
    S.add_parser('version', help='显示版本号')

    # ── schema（v0.3）─────────────────────────────────────────
    ps = S.add_parser('schema', help='要素表 Schema 管理（v0.3）')
    SS = ps.add_subparsers(dest='schema_cmd')

    p = SS.add_parser('define', help='注册一个要素表')
    p.add_argument('name')
    p.add_argument('--states', '-s', help='状态→素数，JSON 或 key=prime,...')
    p.add_argument('--dims',         help='维度标签（逗号分隔）')
    p.add_argument('--desc',         help='描述')

    p = SS.add_parser('record', help='记录一次状态观测')
    p.add_argument('schema')
    p.add_argument('--subject',  '-s', required=True)
    p.add_argument('--states',         required=True,
                   help='状态（逗号分隔），如 high 或 high,degraded')
    p.add_argument('--observer', '-b', default='')
    p.add_argument('--project',        default='')
    p.add_argument('--out',            default='.')

    p = SS.add_parser('export', help='导出 Schema 事件（__all__ 导出全部）')
    p.add_argument('schema')
    p.add_argument('--project', default='')
    p.add_argument('--file', '-f', default=None, help='输出文件路径')
    p.add_argument('--out',        default='.', help='输出目录（__all__ 用）')

    SS.add_parser('list', help='列出已注册的要素表')

    p = SS.add_parser('save', help='保存 Schema 定义为 JSON')
    p.add_argument('schema')
    p.add_argument('file')

    p = SS.add_parser('load', help='从 JSON 加载 Schema 定义')
    p.add_argument('file')

    # ── aggregate（v0.3）──────────────────────────────────────
    p = S.add_parser('aggregate', help='合并多节点日志（v0.3）')
    p.add_argument('--dir',         metavar='DIR')
    p.add_argument('--node-ip',     metavar='IP')
    p.add_argument('--node',        nargs=3, action='append',
                   metavar=('ID','EVENTS','ADJ'))
    p.add_argument('--global-name', default='global')
    p.add_argument('--out', '-o',   default='.')
    p.add_argument('--dry-run',     action='store_true')

    # ─────────────────────────────────────────────────────────
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
        'aggregate':         cmd_aggregate,
    }

    if args.command == 'schema':
        schema_dispatch = {
            'define': cmd_schema_define,
            'record': cmd_schema_record,
            'export': cmd_schema_export,
            'list':   cmd_schema_list,
            'save':   cmd_schema_save,
            'load':   cmd_schema_load,
        }
        sub = getattr(args, 'schema_cmd', None)
        if sub in schema_dispatch:
            schema_dispatch[sub](args)
        else:
            ps.print_help()
    elif args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
