#!/usr/bin/env python3
"""
orchestrator.py — PrimeLog 统一调度中心

职责：
  - 持有 registry / loader / error_log 三件套的引用
  - 提供统一的操作入口（init / scan / export / show_errors / stats / archive）
  - CLI 只负责解析参数，把参数字典交给 Orchestrator 执行
  - 用户脚本通过 primelog.init() 拿到 Orchestrator 实例，或直接用模块级快捷函数

自观测：Orchestrator 本身也注册为 primelog 组件，
        自身的调度行为同样被 error_log 追踪。
"""

import os
import sys
from typing import Optional


class PrimeLogOrchestrator:
    """
    PrimeLog 调度中心。

    所有核心操作都通过这里路由，外部（CLI / 用户脚本）只和它交互。
    """

    def __init__(
        self,
        project:  str = "",
        log_base: str = "./logs",
    ):
        # 延迟导入，避免循环
        from primelog.core.registry  import registry  as _registry
        from primelog.core           import error_log  as _error_log
        from primelog.core.loader    import scan_and_import

        self._registry   = _registry
        self._error_log  = _error_log
        self._scan_fn    = scan_and_import

        self.project  = project
        self.log_base = log_base

        if project:
            self._set_log_dir(project, log_base)

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────

    def _set_log_dir(self, project: str, log_base: str) -> str:
        log_dir = os.path.join(log_base, project) if project else log_base
        os.makedirs(log_dir, exist_ok=True)
        self._error_log.export_dir = log_dir
        return log_dir

    def _resolve_log_dir(self, project: str = "", log_dir: str = "") -> str:
        """优先级：显式 log_dir > log_base+project > log_base+self.project > log_base"""
        if log_dir:
            proj = project or self.project
            return os.path.join(log_dir, proj) if proj else log_dir
        proj = project or self.project
        base = self.log_base
        return os.path.join(base, proj) if proj else base

    # ──────────────────────────────────────────────
    # 核心操作
    # ──────────────────────────────────────────────

    def init(self, project: str, log_base: str = "") -> "PrimeLogOrchestrator":
        """设置项目名，初始化日志目录。返回 self 支持链式调用。"""
        self.project  = project
        if log_base:
            self.log_base = log_base
        log_dir = self._set_log_dir(project, self.log_base)
        print(f"[primelog] 项目 '{project}' 已初始化  日志目录: {log_dir}")
        return self

    def scan(self, directory: str = ".") -> int:
        """扫描目标目录，加载所有含 __loadmark__ 的组件目录。返回加载数量。"""
        directory = os.path.abspath(directory)
        loaded = self._scan_fn(root_override=directory)
        return len(loaded)

    def export(self, project: str = "", output_dir: str = "") -> None:
        """导出当前运行日志（JSON + WL）到项目子目录。"""
        proj  = project or self.project
        base  = output_dir or self.log_base
        out_dir = os.path.join(base, proj) if proj else base
        os.makedirs(out_dir, exist_ok=True)
        self._error_log.export_dir = out_dir
        self._error_log.export_error_log(self._registry)

    def get_stats(self) -> dict:
        """返回当前运行统计（不写文件）。"""
        return self._error_log.get_stats()

    def show_errors(
        self,
        project:  str = "",
        log_dir:  str = "",
        log_file: str = "",
        adj_file: str = "",
    ) -> None:
        """读取最新日志，打印错误事件详情。"""
        import json, glob

        resolved_dir = self._resolve_log_dir(project, log_dir)

        lf = log_file or self._find_latest(resolved_dir, "error_events_*.json")
        af = adj_file or self._find_latest(resolved_dir, "adjacency_matrix_*.json")

        if not lf:
            print(f"❌ 在 {resolved_dir} 下未找到 error_events_*.json")
            return
        if not af:
            print(f"❌ 在 {resolved_dir} 下未找到 adjacency_matrix_*.json")
            return

        with open(af) as f:
            nodes = json.load(f)['nodes']
        with open(lf) as f:
            data = json.load(f)

        prime_map  = data['prime_map']
        rev_map    = {v: k for k, v in prime_map.items()}
        events     = data['events']
        timestamps = data.get('timestamps', [])

        error_count = 0
        print(f"\n错误事件详情  ({lf})\n{'─'*70}")
        for i, (t, caller, callee, composite, log_val) in enumerate(events):
            if composite == 1:
                continue
            error_count += 1
            errors = self._decode(composite, rev_map)
            ts = timestamps[i] if i < len(timestamps) else ""
            cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
            ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
            print(f"t={t:4d}  {cn:35s} → {ce:35s}")
            print(f"       errors={errors}  composite={composite}  {ts}")

        if error_count == 0:
            print("  ✅ 无错误事件")
        print(f"{'─'*70}\n共 {error_count} 个错误事件（总事件 {len(events)} 条）")

    def stats(
        self,
        project:  str = "",
        log_dir:  str = "",
        log_file: str = "",
    ) -> None:
        """读取最新日志，打印错误分布统计。"""
        import json, glob
        from collections import Counter

        resolved_dir = self._resolve_log_dir(project, log_dir)
        lf = log_file or self._find_latest(resolved_dir, "error_events_*.json")
        af = self._find_latest(resolved_dir, "adjacency_matrix_*.json")

        if not lf:
            print(f"❌ 在 {resolved_dir} 下未找到 error_events_*.json")
            return

        with open(lf) as f:
            data = json.load(f)
        nodes = []
        if af:
            with open(af) as f2:
                nodes = json.load(f2)['nodes']

        rev_map = {v: k for k, v in data['prime_map'].items()}
        events  = data['events']

        caller_errors = Counter()
        callee_errors = Counter()
        total_errors  = Counter()

        for t, caller, callee, composite, _ in events:
            if composite == 1:
                continue
            errors = self._decode(composite, rev_map)
            cn = nodes[caller] if caller < len(nodes) else f"#{caller}"
            ce = nodes[callee] if callee < len(nodes) else f"#{callee}"
            for e in errors:
                total_errors[e]             += 1
                caller_errors[(cn, e)]      += 1
                callee_errors[(ce, e)]      += 1

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

    def archive(
        self,
        project:    str = "",
        log_dir:    str = "",
        keep:       int = 30,
        compressor: str = "tar",
    ) -> None:
        """归档旧日志，调用 log_librarian。"""
        from primelog.logs.log_librarian import main as librarian_main

        resolved_dir = self._resolve_log_dir(project, log_dir)
        argv = ['log_librarian', '--keep', str(keep), '--compressor', compressor]
        if resolved_dir:
            argv += ['--log-dir', resolved_dir]

        sys.argv = argv
        librarian_main()

    def register(
        self,
        files:     list,
        type_:     str,
        project:   str = "",
        signature: str = "",
    ) -> None:
        """给 .py 文件打上 PrimeLog 印章。"""
        from primelog.tools.register_file import stamp, stamp_multiple
        proj = project or self.project or ""
        if len(files) == 1:
            ok, msg = stamp(files[0], type_=type_, project=proj, signature=signature)
            print(msg)
        else:
            stamp_multiple(files, type_=type_, project=proj, signature=signature)

    def loadmark(
        self,
        directory: str,
        remove:    bool = False,
        recursive: bool = False,
        max_depth: int  = -1,
    ) -> None:
        """管理 __loadmark__ 标记文件。"""
        from primelog.tools.loadmark import run as loadmark_run
        loadmark_run(
            directory=directory,
            remove=remove,
            recursive=recursive,
            max_depth=max_depth,
        )

    # ──────────────────────────────────────────────
    # 内部工具方法
    # ──────────────────────────────────────────────

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


# ── 模块级默认实例（import primelog 直接可用）──────────────
_default_orchestrator = PrimeLogOrchestrator()
