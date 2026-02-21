"""
PrimeLog — Decompose Anything. Understand Everything.

快速开始：

    import primelog

    primelog.init('my-project')           # 设置项目名

    @primelog.component('my-project.my.service', type_='service')
    class MyService:
        def run(self): ...

    primelog.scan('./my_project')         # 加载组件
    # ... 正常运行你的代码 ...
    primelog.export()                     # → ./logs/my-project/

    # CLI：
    # primelog show-errors --project my-project
    # primelog stats       --project my-project
    # primelog archive     --project my-project --keep 30
"""

from primelog.core.registry  import Registry, registry
from primelog.core.error_log import (
    record_event,
    export_error_log,
    get_stats,
    register_error_type,
    decode_errors,
    prime_map,
)
from primelog.core.orchestrator import PrimeLogOrchestrator

__version__ = "0.1.4"
__author__  = "RoseHammer"
__license__ = "MPL-2.0"

# ── 模块级默认 Orchestrator 实例（与 cli.py 共享同一个单例）──
from primelog.core.orchestrator import _default_orchestrator as _orch


# ── 零概念装饰器（唯一不经过 Orchestrator 的入口，因为它是注册行为本身）──
def component(name: str, type_: str = "component", signature: str = ""):
    """
    零概念接入装饰器。自动注册 + 调用追踪 + 错误记录。

    用法::

        @primelog.component('my-project.algorithm.pso', type_='algorithm')
        class PSO:
            def run(self): ...
    """
    return registry.register(name=name, type_=type_, signature=signature)


# ── 模块级快捷函数，全部委托给默认 Orchestrator ────────────────

def init(project: str, log_base: str = "./logs") -> PrimeLogOrchestrator:
    """初始化项目名，返回 Orchestrator 实例（可忽略）。"""
    return _orch.init(project, log_base)


def scan(directory: str = ".") -> int:
    """扫描并加载目标目录下所有含 __loadmark__ 的组件目录。"""
    return _orch.scan(directory)


def export(project: str = "", output_dir: str = "") -> None:
    """导出当前运行日志（JSON + WL）到项目子目录。"""
    _orch.export(project=project, output_dir=output_dir)


def show_errors(project: str = "", log_dir: str = "", log_file: str = "") -> None:
    """打印错误事件详情。"""
    _orch.show_errors(project=project, log_dir=log_dir, log_file=log_file)


def stats(project: str = "", log_dir: str = "", log_file: str = "") -> None:
    """打印错误分布统计。"""
    _orch.stats(project=project, log_dir=log_dir, log_file=log_file)


def archive(project: str = "", log_dir: str = "",
            keep: int = 30, compressor: str = "tar") -> None:
    """归档旧日志。"""
    _orch.archive(project=project, log_dir=log_dir,
                  keep=keep, compressor=compressor)


__all__ = [
    # Orchestrator
    "PrimeLogOrchestrator",
    # registry
    "registry", "Registry",
    # 装饰器
    "component",
    # 快捷函数
    "init", "scan", "export",
    "show_errors", "stats", "archive",
    # error_log 底层
    "get_stats", "record_event", "export_error_log",
    "register_error_type", "decode_errors", "prime_map",
]
