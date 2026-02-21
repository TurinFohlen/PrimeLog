"""
PrimeLog — Decompose Anything. Understand Everything.

快速开始：

    import primelog

    # 方式一：脚本开头初始化一次，后面全自动
    primelog.init('projectA')

    @primelog.component('projectA.my.service', type_='service')
    class MyService:
        def run(self): ...

    primelog.export()   # 自动写到 logs/projectA/

    # 方式二：只在导出时指定项目名
    primelog.export(project='projectA', output_dir='./logs')

    # CLI：
    # primelog show-errors --project projectA
    # primelog stats       --project projectA
    # primelog archive     --project projectA --keep 30
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

__version__ = "0.1.1"
__author__  = "RoseHammer"
__license__ = "MPL-2.0"

# ── 全局项目名（init() 设置后所有操作自动使用）──────────────────
_current_project: str = ""


def init(project: str, log_base: str = "./logs") -> None:
    """
    在脚本开头调用一次，设置当前项目名。
    后续 export() 无需再传 project 参数。

    用法::

        primelog.init('pocket-optimizer')
        # 日志自动写到 ./logs/pocket-optimizer/
    """
    global _current_project
    import primelog.core.error_log as _el
    import os

    _current_project = project
    project_log_dir  = os.path.join(log_base, project)
    os.makedirs(project_log_dir, exist_ok=True)
    _el.export_dir   = project_log_dir
    print(f"[primelog] 项目 '{project}' 已初始化  日志目录: {project_log_dir}")


def component(name: str, type_: str = "component", signature: str = ""):
    """
    零概念接入装饰器。

    用法::

        @primelog.component('projectA.my.service', type_='service')
        class MyService:
            def run(self): ...

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


def export(project: str = "", output_dir: str = "./logs") -> None:
    """
    导出当前运行的所有日志（JSON + WL 格式）。

    项目名优先级：
        1. 本次 export(project='xxx') 显式传入
        2. 之前 init('xxx') 设置的全局项目名
        3. 两者都没有 → 直接写到 output_dir 根目录

    用法::

        primelog.init('projectA')
        primelog.export()                         # → ./logs/projectA/

        primelog.export(project='projectA')       # → ./logs/projectA/
        primelog.export(project='projectA',
                        output_dir='/data/logs')  # → /data/logs/projectA/
    """
    import primelog.core.error_log as _el
    import os

    proj = project or _current_project
    out  = os.path.join(output_dir, proj) if proj else output_dir
    os.makedirs(out, exist_ok=True)
    _el.export_dir = out
    export_error_log(registry)


__all__ = [
    "registry",
    "Registry",
    "init",
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
