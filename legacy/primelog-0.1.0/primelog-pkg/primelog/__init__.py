"""
PrimeLog — Decompose Anything. Understand Everything.

快速开始：

    import primelog

    @primelog.component('my.service', type_='service')
    class MyService:
        def run(self):
            ...

    # 或者用 CLI 扫描整个目录：
    # primelog scan ./my_project
    # primelog show-errors
    # primelog stats
    # primelog archive
"""

from primelog.core.registry import Registry, registry
from primelog.core.error_log import (
    record_event,
    export_error_log,
    get_stats,
    register_error_type,
    decode_errors,
    prime_map,
)

__version__ = "0.1.0"
__author__  = "RoseHammer"
__license__ = "MPL-2.0"


def component(name: str, type_: str = "component", signature: str = ""):
    """
    零概念接入装饰器。

    用法::

        @primelog.component('my.service', type_='service')
        class MyService:
            def run(self): ...

        @primelog.component('my.util', type_='util')
        def my_util(x):
            return x * 2

    效果：
    - 自动注册到全局 registry
    - 所有方法调用自动进入 component_context（追踪依赖 + 记录错误）
    - 无需手动 import registry 或 error_log
    """
    return registry.register(name=name, type_=type_, signature=signature)


def scan(directory: str = ".") -> int:
    """
    扫描并加载目标目录下所有含 __loadmark__ 的组件目录。
    返回已加载的组件数量。
    """
    from primelog.core.loader import scan_and_import
    loaded = scan_and_import(root_override=directory)
    return len(loaded)


def export(output_dir: str = ".") -> None:
    """导出当前运行的所有日志（JSON + WL 格式）。"""
    import primelog.core.error_log as _el
    _el.export_dir = output_dir
    export_error_log(registry)


__all__ = [
    "registry",
    "Registry",
    "component",
    "scan",
    "export",
    "get_stats",
    "record_event",
    "export_error_log",
    "register_error_type",
    "decode_errors",
    "prime_map",
]
