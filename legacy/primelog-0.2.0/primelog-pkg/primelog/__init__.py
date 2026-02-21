"""
PrimeLog — Decompose Anything. Understand Everything.  v0.2.0

快速上手：

    import primelog

    primelog.init('my-project')

    @primelog.component('my-project.algo.pso', type_='algorithm')
    class PSO:
        def run(self): ...

    primelog.scan('./my_project')
    # ... 正常运行你的代码 ...
    primelog.export()

    # 分析
    primelog.show_errors()
    primelog.stats()
    primelog.histogram()
    primelog.timeline()
    primelog.convert(fmt='csv')
"""

from primelog.core.registry  import Registry, registry
from primelog.core.error_log import (
    record_event, export_error_log, get_stats,
    register_error_type, decode_errors, prime_map,
)
from primelog.core.orchestrator import PrimeLogOrchestrator, _default_orchestrator as _orch

__version__ = "0.2.0"
__author__  = "RoseHammer"
__license__ = "MPL-2.0"


# ── 唯一不经过 Orchestrator 的入口（注册行为本身）─────────────
def component(name: str, type_: str = "component", signature: str = ""):
    """零概念接入装饰器。自动注册 + 调用追踪 + 错误记录。"""
    return registry.register(name=name, type_=type_, signature=signature)


# ── 所有操作委托给同一个 Orchestrator 单例 ──────────────────────

def init(project: str, log_base: str = "./logs") -> PrimeLogOrchestrator:
    """初始化项目名 + 日志目录 + 切换事件状态。"""
    return _orch.init(project, log_base)

def scan(directory: str = ".") -> int:
    """扫描并加载目标目录下所有含 __loadmark__ 的组件目录。"""
    return _orch.scan(directory)

def export(project: str = "", output_dir: str = "") -> None:
    """导出当前项目日志（JSON + WL）。"""
    _orch.export(project=project, output_dir=output_dir)

def show_errors(project: str = "", log_dir: str = "", log_file: str = "") -> None:
    """打印错误事件详情。"""
    _orch.show_errors(project=project, log_dir=log_dir, log_file=log_file)

def stats(project: str = "", log_dir: str = "", log_file: str = "") -> None:
    """打印错误分布统计。"""
    _orch.stats(project=project, log_dir=log_dir, log_file=log_file)

def histogram(project: str = "", log_dir: str = "", log_file: str = "",
              top: int = 15, width: int = 60, log_scale: bool = False) -> None:
    """ASCII 错误频率直方图。"""
    _orch.histogram(project=project, log_dir=log_dir, log_file=log_file,
                    top=top, width=width, log_scale=log_scale)

def timeline(project: str = "", log_dir: str = "", log_file: str = "",
             mode: str = "all", interval: str = "1m") -> None:
    """ASCII 时间线可视化。"""
    _orch.timeline(project=project, log_dir=log_dir, log_file=log_file,
                   mode=mode, interval=interval)

def timeline_analysis(project: str = "", log_dir: str = "",
                      log_file: str = "") -> None:
    """按分钟统计事件数量（轻量分析）。"""
    _orch.timeline_analysis(project=project, log_dir=log_dir, log_file=log_file)

def convert(project: str = "", log_dir: str = "", log_file: str = "",
            fmt: str = "csv", output: str = "") -> None:
    """将日志导出为 CSV / JSONL / Elasticsearch 格式。"""
    _orch.convert(project=project, log_dir=log_dir, log_file=log_file,
                  fmt=fmt, output=output)

def fft_prep(project: str = "", log_dir: str = "", log_file: str = "",
             mode: str = "interval", bin_size: float = 1.0,
             output: str = "") -> None:
    """为 FFT 频域分析准备时间序列数据。"""
    _orch.fft_prep(project=project, log_dir=log_dir, log_file=log_file,
                   mode=mode, bin_size=bin_size, output=output)

def archive(project: str = "", keep: int = 30, compressor: str = "tar") -> None:
    """归档旧日志。"""
    _orch.archive(project=project, keep=keep, compressor=compressor)


__all__ = [
    "PrimeLogOrchestrator",
    "registry", "Registry",
    "component",
    "init", "scan", "export",
    "show_errors", "stats",
    "histogram", "timeline", "timeline_analysis",
    "convert", "fft_prep",
    "archive",
    "get_stats", "record_event", "export_error_log",
    "register_error_type", "decode_errors", "prime_map",
]
