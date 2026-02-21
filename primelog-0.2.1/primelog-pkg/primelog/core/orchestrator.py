#!/usr/bin/env python3
"""
orchestrator.py — PrimeLog 统一调度中心  v0.2.0

职责：
  - 持有 registry / loader / error_log 三件套引用
  - 提供统一操作入口（init / scan / export / show_errors / stats /
    archive / histogram / timeline / convert / fft_prep / loadmark / register）
  - CLI 只负责解析参数，把参数字典交给 Orchestrator 执行
  - 自观测：Orchestrator 本身注册为 primelog.core.orchestrator 组件，
    自身的调度行为同样被 error_log 追踪

全局状态隔离：
  每个项目拥有独立的 _events / _timed_events 列表（存储在 _project_state），
  切换项目时自动 swap，解决多项目并发写入问题。
"""

import os
import sys
from typing import Optional


# ── 全局项目事件状态隔离表 ──────────────────────────────────────
# key = project name, value = {"events": [...], "timed_events": [...]}
_project_state: dict = {}


def _swap_project_state(error_log_module, project: str) -> None:
    """
    将 error_log 模块的全局 _events/_timed_events 指针
    切换到指定项目的独立列表。
    """
    if not project:
        return

    # 先把当前内容存回上一个项目（如果有）
    current = getattr(error_log_module, '_current_project_key', None)
    if current and current in _project_state:
        _project_state[current]['events']       = error_log_module._events
        _project_state[current]['timed_events'] = error_log_module._timed_events

    # 初始化新项目
    if project not in _project_state:
        _project_state[project] = {'events': [], 'timed_events': []}

    # 切换
    error_log_module._events       = _project_state[project]['events']
    error_log_module._timed_events = _project_state[project]['timed_events']
    error_log_module._current_project_key = project


class PrimeLogOrchestrator:
    """
    PrimeLog 调度中心。

    所有核心操作都通过这里路由，外部（CLI / 用户脚本）只和它交互。
    自身注册为 primelog.core.orchestrator 组件，调度行为同样被追踪。
    """

    def __init__(self, project: str = "", log_base: str = "./logs"):
        from primelog.core.registry import registry  as _registry
        from primelog.core          import error_log  as _error_log
        from primelog.core.loader   import scan_and_import

        self._registry  = _registry
        self._el        = _error_log
        self._scan_fn   = scan_and_import

        self.project  = project
        self.log_base = log_base

        if project:
            self._activate(project, log_base)

        # 自观测在模块末尾通过哨兵类完成，这里不注册类本身

    # ─────────────────────────────────────────────────────────────
    # 内部工具
    # ─────────────────────────────────────────────────────────────

    def _activate(self, project: str, log_base: str = "") -> str:
        """切换到目标项目：swap 事件状态 + 设置 export_dir"""
        base    = log_base or self.log_base
        log_dir = os.path.join(base, project) if project else base
        os.makedirs(log_dir, exist_ok=True)
        _swap_project_state(self._el, project)
        self._el.export_dir = log_dir
        return log_dir

    def _resolve_log_dir(self, project: str = "", log_dir: str = "") -> str:
        if log_dir:
            proj = project or self.project
            return os.path.join(log_dir, proj) if proj else log_dir
        proj = project or self.project
        return os.path.join(self.log_base, proj) if proj else self.log_base

    @staticmethod
    def _find_latest(log_dir: str, pattern: str) -> Optional[str]:
        import glob
        files = glob.glob(os.path.join(log_dir, pattern))
        return max(files, key=os.path.getmtime) if files else None

    @staticmethod
    def _decode(composite: int, rev_map: dict) -> list:
        remaining = composite
        errors = []
        for p, name in rev_map.items():
            if p > 1 and remaining % p == 0:
                errors.append(name)
                while remaining % p == 0:
                    remaining //= p
        return errors or ['unknown']

    # ─────────────────────────────────────────────────────────────
    # 核心生命周期
    # ─────────────────────────────────────────────────────────────

    def init(self, project: str, log_base: str = "") -> "PrimeLogOrchestrator":
        """设置项目名，初始化日志目录，swap 事件状态。返回 self 支持链式。"""
        self.project  = project
        if log_base:
            self.log_base = log_base
        log_dir = self._activate(project, self.log_base)
        print(f"[primelog] 项目 '{project}' 已初始化  日志目录: {log_dir}")
        return self

    def scan(self, directory: str = ".") -> int:
        """扫描目标目录，加载所有含 __loadmark__ 的组件目录。"""
        loaded = self._scan_fn(root_override=os.path.abspath(directory))
        return len(loaded)

    def export(self, project: str = "", output_dir: str = "") -> None:
        """导出当前项目日志（JSON + WL）。"""
        proj  = project or self.project
        base  = output_dir or self.log_base
        out   = os.path.join(base, proj) if proj else base
        os.makedirs(out, exist_ok=True)
        if proj:
            _swap_project_state(self._el, proj)
        self._el.export_dir = out
        self._el.export_error_log(self._registry)

    def get_stats(self) -> dict:
        return self._el.get_stats()

    # ─────────────────────────────────────────────────────────────
    # 日志分析
    # ─────────────────────────────────────────────────────────────

    def show_errors(self, project: str = "", log_dir: str = "",
                    log_file: str = "", adj_file: str = "") -> None:
        import json
        d = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        af = adj_file or self._find_latest(d, "adjacency_matrix_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        if not af:
            print(f"❌ 在 {d} 下未找到 adjacency_matrix_*.json"); return

        with open(af) as f: nodes = json.load(f)['nodes']
        with open(lf) as f: data  = json.load(f)

        rev_map    = {v: k for k, v in data['prime_map'].items()}
        events     = data['events']
        timestamps = data.get('timestamps', [])
        errors_found = 0

        print(f"\n错误事件详情  ({lf})\n{'─'*70}")
        for i, (t, caller, callee, composite, _) in enumerate(events):
            if composite == 1: continue
            errors_found += 1
            errors = self._decode(composite, rev_map)
            ts = timestamps[i] if i < len(timestamps) else ""
            cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
            ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
            print(f"t={t:4d}  {cn:35s} → {ce:35s}")
            print(f"       errors={errors}  composite={composite}  {ts}")
        if not errors_found:
            print("  ✅ 无错误事件")
        print(f"{'─'*70}\n共 {errors_found} 个错误事件（总事件 {len(events)} 条）")

    def stats(self, project: str = "", log_dir: str = "", log_file: str = "") -> None:
        import json
        from collections import Counter
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        af = self._find_latest(d, "adjacency_matrix_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return

        with open(lf) as f: data = json.load(f)
        nodes = []
        if af:
            with open(af) as f2: nodes = json.load(f2)['nodes']

        rev_map       = {v: k for k, v in data['prime_map'].items()}
        caller_errors = Counter()
        callee_errors = Counter()
        total_errors  = Counter()

        for t, caller, callee, composite, _ in data['events']:
            if composite == 1: continue
            errors = self._decode(composite, rev_map)
            cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
            ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
            for e in errors:
                total_errors[e] += 1
                caller_errors[(cn, e)] += 1
                callee_errors[(ce, e)] += 1

        print(f"\n错误统计  ({lf})\n{'─'*60}")
        print("\n全局错误类型分布:")
        for err, cnt in total_errors.most_common():
            print(f"  {err:25s}: {cnt}")
        print("\n按调用者统计（Top 10）:")
        for (comp, err), cnt in caller_errors.most_common(10):
            print(f"  {comp:35s}  {err:20s}: {cnt}")
        print("\n按被调用者统计（Top 10）:")
        for (comp, err), cnt in callee_errors.most_common(10):
            print(f"  {comp:35s}  {err:20s}: {cnt}")

    def histogram(self, project: str = "", log_dir: str = "", log_file: str = "",
                  top: int = 15, width: int = 60, log_scale: bool = False) -> None:
        """ASCII 错误频率直方图"""
        from primelog.tools.histogram import run as _run
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json") or ""
        _run(log_file=lf, log_dir=d, top=top, width=width, log_scale=log_scale)

    def timeline(self, project: str = "", log_dir: str = "", log_file: str = "",
                 mode: str = "all", interval: str = "1m", width: int = 80,
                 height: int = 20, top: int = 5, detect_anomaly: bool = False,
                 anomaly_threshold: float = 3.0) -> None:
        """ASCII 时间线可视化（热力图 / 冲击波图 / 多错误时间线）"""
        from primelog.tools.timeline_visualization import run as _run
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf, mode=mode, interval=interval, width=width, height=height,
             top=top, detect_anomaly=detect_anomaly,
             anomaly_threshold=anomaly_threshold)

    def timeline_analysis(self, project: str = "", log_dir: str = "",
                          log_file: str = "") -> None:
        """按分钟统计事件数量（轻量分析）"""
        from primelog.tools.timeline_analysis import run as _run
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf)

    def convert(self, project: str = "", log_dir: str = "", log_file: str = "",
                fmt: str = "csv", output: str = "", index: str = "primelog",
                start: str = "", end: str = "",
                error_types: str = "", component: str = "") -> None:
        """将日志导出为 CSV / JSONL / Elasticsearch Bulk 格式"""
        from primelog.tools.exporter import run as _run
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf, fmt=fmt, output=output, index=index, start=start,
             end=end, error_types=error_types, component=component)

    def fft_prep(self, project: str = "", log_dir: str = "", log_file: str = "",
                 mode: str = "interval", bin_size: float = 1.0,
                 output: str = "") -> None:
        """为 FFT 频域分析准备时间序列数据"""
        from primelog.tools.preprocess_events_for_fft import run as _run
        d  = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(d, "error_events_*.json")
        if not lf:
            print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf, mode=mode, bin_size=bin_size, output=output)

    # ─────────────────────────────────────────────────────────────
    # 维护工具
    # ─────────────────────────────────────────────────────────────

    def archive(self, project: str = "", log_dir: str = "",
                keep: int = 30, compressor: str = "tar") -> None:
        from primelog.logs.log_librarian import main as librarian_main
        d = self._resolve_log_dir(project, log_dir)
        sys.argv = ['log_librarian', '--keep', str(keep),
                    '--compressor', compressor]
        if d: sys.argv += ['--log-dir', d]
        librarian_main()

    def register(self, files: list, type_: str,
                 project: str = "", signature: str = "") -> None:
        from primelog.tools.register_file import stamp, stamp_multiple
        proj = project or self.project or ""
        if len(files) == 1:
            ok, msg = stamp(files[0], type_=type_, project=proj, signature=signature)
            print(msg)
        else:
            stamp_multiple(files, type_=type_, project=proj, signature=signature)

    def loadmark(self, directory: str, remove: bool = False,
                 recursive: bool = False, max_depth: int = -1) -> None:
        from primelog.tools.loadmark import run as loadmark_run
        loadmark_run(directory=directory, remove=remove,
                     recursive=recursive, max_depth=max_depth)


# ── 自观测哨兵：轻量类仅用于注册，不影响 Orchestrator 内部方法 ──
class _OrchestratorSentinel:
    """仅用于自观测注册的哨兵类，不包含任何业务逻辑。"""
    def dispatch(self, command: str, **kwargs): ...

# ── 模块级默认单例（与 __init__.py 和 cli.py 共享）─────────────
_default_orchestrator = PrimeLogOrchestrator()

# 注册哨兵（延迟到单例创建之后，避免循环）
try:
    from primelog.core.registry import registry as _reg
    _reg.register(
        name      = 'primelog.core.orchestrator',
        type_     = 'orchestrator',
        signature = 'dispatch(command, **kwargs)',
    )(_OrchestratorSentinel)
except Exception:
    pass
