#!/usr/bin/env python3
"""
orchestrator.py — PrimeLog 统一调度中心  v0.2.2

三项核心改进
============
1. 自观测
   init / scan / export / show_errors / stats / histogram / timeline /
   timeline_analysis / convert / fft_prep 均通过
   component_context('primelog.core.orchestrator') 执行。
   Orchestrator 本身的调用链、异常都被 error_log 追踪。

2. 多项目并发隔离
   _project_state 现在同时隔离：
     _events / _timed_events / export_dir / _event_counter
   _swap_project_state 由 threading.Lock 保护，消除并发切换时的竞态。

3. 函数名推断关系类型（由 registry.py 实现）
   Orchestrator 本身是 primelog.core.orchestrator（orchestrator 类型）。
"""

import os
import sys
import threading
from typing import Optional


def _swap_project_state(error_log_module, project: str,
                        export_dir: str = "") -> None:
    """
    绑定当前线程到指定项目的事件 store。
    底层由 error_log._init_project + _bind_thread 完成，线程安全。
    """
    if not project:
        return
    error_log_module._init_project(project, export_dir or ".")
    error_log_module._bind_thread(project)
    # 向后兼容：同步模块级 export_dir（单线程场景仍需要）
    if export_dir:
        error_log_module.export_dir = export_dir


class PrimeLogOrchestrator:
    """
    PrimeLog 调度中心（v0.2.2）。

    · 自观测：所有外部操作都在 component_context 内执行。
    · 多项目隔离：每个项目独占 events/export_dir/event_counter。
    · 函数名推断关系类型：由 registry._analyze_dependencies 完成。
    """

    def __init__(self, project: str = "", log_base: str = "./logs"):
        from primelog.core.registry import registry as _registry
        from primelog.core          import error_log as _error_log
        from primelog.core.loader   import scan_and_import

        self._registry = _registry
        self._el       = _error_log
        self._scan_fn  = scan_and_import

        self.project  = project
        self.log_base = log_base

        if project:
            self._activate(project, log_base)

    # ─────────────────────────────────────────────────────────────
    # 内部工具
    # ─────────────────────────────────────────────────────────────

    def _activate(self, project: str, log_base: str = "") -> str:
        """切换到目标项目：建目录 + swap 全部状态（含 export_dir）"""
        base    = log_base or self.log_base
        log_dir = os.path.join(base, project) if project else base
        os.makedirs(log_dir, exist_ok=True)
        _swap_project_state(self._el, project, export_dir=log_dir)
        return log_dir

    def _ctx(self):
        """返回自观测上下文管理器"""
        return self._registry.component_context('primelog.core.orchestrator')

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
    # 核心生命周期（自观测）
    # ─────────────────────────────────────────────────────────────

    def init(self, project: str, log_base: str = "") -> "PrimeLogOrchestrator":
        """设置项目名，初始化日志目录，swap 全部状态。"""
        self.project = project
        if log_base:
            self.log_base = log_base
        with self._ctx():
            log_dir = self._activate(project, self.log_base)
        print(f"[primelog] 项目 '{project}' 已初始化  日志目录: {log_dir}")
        return self

    def scan(self, directory: str = ".") -> int:
        """扫描目标目录，加载所有含 __loadmark__ 的组件目录。"""
        with self._ctx():
            loaded = self._scan_fn(root_override=os.path.abspath(directory))
        return len(loaded)

    def export(self, project: str = "", output_dir: str = "") -> None:
        """导出当前项目日志（JSON + WL）。"""
        proj = project or self.project
        base = output_dir or self.log_base
        out  = os.path.join(base, proj) if proj else base
        os.makedirs(out, exist_ok=True)
        with self._ctx():
            if proj:
                _swap_project_state(self._el, proj, export_dir=out)
            else:
                self._el.export_dir = out
            self._el.export_error_log(self._registry)

    def get_stats(self) -> dict:
        return self._el.get_stats()

    # ─────────────────────────────────────────────────────────────
    # 日志分析（自观测）
    # ─────────────────────────────────────────────────────────────

    def show_errors(self, project: str = "", log_dir: str = "",
                    log_file: str = "", adj_file: str = "") -> None:
        import json
        with self._ctx():
            d  = self._resolve_log_dir(project, log_dir)
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

    def stats(self, project: str = "", log_dir: str = "",
              log_file: str = "") -> None:
        import json
        from collections import Counter
        with self._ctx():
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

    def histogram(self, project: str = "", log_dir: str = "",
                  log_file: str = "", top: int = 15, width: int = 60,
                  log_scale: bool = False) -> None:
        from primelog.tools.histogram import run as _run
        with self._ctx():
            d  = self._resolve_log_dir(project, log_dir)
            lf = log_file or self._find_latest(d, "error_events_*.json") or ""
        _run(log_file=lf, log_dir=d, top=top, width=width, log_scale=log_scale)

    def timeline(self, project: str = "", log_dir: str = "",
                 log_file: str = "", mode: str = "all", interval: str = "1m",
                 width: int = 80, height: int = 20, top: int = 5,
                 detect_anomaly: bool = False,
                 anomaly_threshold: float = 3.0) -> None:
        from primelog.tools.timeline_visualization import run as _run
        with self._ctx():
            d  = self._resolve_log_dir(project, log_dir)
            lf = log_file or self._find_latest(d, "error_events_*.json")
            if not lf:
                print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf, mode=mode, interval=interval, width=width, height=height,
             top=top, detect_anomaly=detect_anomaly,
             anomaly_threshold=anomaly_threshold)

    def timeline_analysis(self, project: str = "", log_dir: str = "",
                          log_file: str = "") -> None:
        from primelog.tools.timeline_analysis import run as _run
        with self._ctx():
            d  = self._resolve_log_dir(project, log_dir)
            lf = log_file or self._find_latest(d, "error_events_*.json")
            if not lf:
                print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf)

    def convert(self, project: str = "", log_dir: str = "",
                log_file: str = "", fmt: str = "csv", output: str = "",
                index: str = "primelog", start: str = "", end: str = "",
                error_types: str = "", component: str = "") -> None:
        from primelog.tools.exporter import run as _run
        with self._ctx():
            d  = self._resolve_log_dir(project, log_dir)
            lf = log_file or self._find_latest(d, "error_events_*.json")
            if not lf:
                print(f"❌ 在 {d} 下未找到 error_events_*.json"); return
        _run(lf, fmt=fmt, output=output, index=index, start=start,
             end=end, error_types=error_types, component=component)

    def fft_prep(self, project: str = "", log_dir: str = "",
                 log_file: str = "", mode: str = "interval",
                 bin_size: float = 1.0, output: str = "") -> None:
        from primelog.tools.preprocess_events_for_fft import run as _run
        with self._ctx():
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
            ok, msg = stamp(files[0], type_=type_, project=proj,
                            signature=signature)
            print(msg)
        else:
            stamp_multiple(files, type_=type_, project=proj,
                           signature=signature)

    def loadmark(self, directory: str, remove: bool = False,
                 recursive: bool = False, max_depth: int = -1) -> None:
        from primelog.tools.loadmark import run as loadmark_run
        loadmark_run(directory=directory, remove=remove,
                     recursive=recursive, max_depth=max_depth)


# ── 自观测哨兵 ────────────────────────────────────────────────
class _OrchestratorSentinel:
    """仅用于注册为 primelog.core.orchestrator 组件的哨兵。"""
    def dispatch(self, command: str, **kwargs): ...


# ── 模块级默认单例 ────────────────────────────────────────────
_default_orchestrator = PrimeLogOrchestrator()

# 注册哨兵（在单例创建后，避免循环引用）
try:
    from primelog.core.registry import registry as _reg
    _reg.register(
        name      = 'primelog.core.orchestrator',
        type_     = 'orchestrator',
        signature = 'dispatch(command, **kwargs)',
    )(_OrchestratorSentinel)
except Exception:
    pass
