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


# ── 外部 API 调用追踪（稻草人 / Scarecrow）────────────────────

import os as _os

def _http_status_to_error(status: int) -> str:
    """HTTP 状态码 → prime_map 错误键。"""
    _map = {
        400: "http_400", 401: "http_401", 403: "http_403", 404: "http_404",
        500: "http_500", 502: "http_502", 503: "http_503", 504: "http_504",
    }
    return _map.get(status, "http_500")


def _prepare_request(cfg: dict) -> dict:
    """从组件 metadata 构造 requests.request 所需参数。"""
    req = {
        "method":  cfg.get("method", "GET"),
        "url":     cfg["url"],
        "timeout": cfg.get("timeout", 10),
    }
    # 请求头透传
    if "headers" in cfg:
        req["headers"] = dict(cfg["headers"])
    # 认证
    auth = cfg.get("auth")
    if auth:
        atype = auth.get("type", "")
        if atype == "bearer":
            token = auth["token"]
            if isinstance(token, str) and token.startswith("env:"):
                token = _os.environ.get(token[4:], "")
            req.setdefault("headers", {})
            req["headers"]["Authorization"] = f"Bearer {token}"
        elif atype == "basic":
            user = auth.get("username", "")
            pwd  = auth.get("password", "")
            if isinstance(user, str) and user.startswith("env:"):
                user = _os.environ.get(user[4:], "")
            if isinstance(pwd, str) and pwd.startswith("env:"):
                pwd = _os.environ.get(pwd[4:], "")
            req["auth"] = (user, pwd)
    # 其余字段直接透传（params / json / data 等）
    for key in ("params", "json", "data", "cookies", "verify", "cert"):
        if key in cfg:
            req[key] = cfg[key]
    return req


def _get_current_project() -> str:
    """从线程本地变量读取当前绑定的项目名，找不到则返回空字符串。"""
    from primelog.core import error_log as _el
    key = getattr(_el._thread_local, "project_key", None)
    return key or ""


def register_external(name: str, url: str,
                       method: str = "GET",
                       timeout: int = 10,
                       auth: dict = None,
                       headers: dict = None,
                       project: str = "") -> None:
    """
    手动注册一个外部服务为虚拟组件。
    name    : 服务短名，最终组件名为 "{project}.{name}"
    url     : 服务地址
    method  : 默认 HTTP 方法
    timeout : 超时秒数
    auth    : {"type": "bearer"/"basic", ...}
    project : 项目名，省略时自动从线程上下文读取
    """
    proj = project or _get_current_project()
    if not proj:
        raise ValueError("register_external 需要项目名：请传入 project= 或先调用 primelog.init()")
    comp_name = f"{proj}.{name}"
    cfg = {"url": url, "method": method, "timeout": timeout}
    if auth:
        cfg["auth"] = auth
    if headers:
        cfg["headers"] = headers

    registry.register(
        name=comp_name,
        type_="external",
        signature=f"{method} {url}",
    )(None)
    spec = registry.get_spec(comp_name)
    if spec is not None:
        spec.metadata = cfg


def _register_external_components(project: str,
                                   config_dir: str = "") -> None:
    """
    从 postoffice/{project}/missionlist/externals.json 批量注册外部组件。
    由 primelog.init() 自动调用；也可手动调用。
    """
    from pathlib import Path
    import json

    base = Path(config_dir) if config_dir else (Path.cwd() / "postoffice" / project)
    ext_path = base / "missionlist" / "externals.json"
    if not ext_path.exists():
        return

    with open(ext_path) as f:
        externals = json.load(f)

    for name, cfg in externals.items():
        comp_name = f"{project}.{name}"
        registry.register(
            name=comp_name,
            type_=cfg.get("type", "external"),
            signature=f"{cfg.get('method','GET')} {cfg['url']}",
        )(None)
        spec = registry.get_spec(comp_name)
        if spec is not None:
            spec.metadata = cfg

    if externals:
        import logging
        logging.getLogger("primelog").info(
            f"[{project}] 注册 {len(externals)} 个外部组件: {list(externals)}"
        )


def call_external(name: str,
                  method: str = None,
                  url:    str = None,
                  project: str = "",
                  **kwargs):
    """
    调用外部 API，自动记录为组件调用事件。

    参数：
        name    外部组件短名（不含项目前缀），需已通过 externals.json 或
                register_external() 注册。
        method  覆盖配置中的 HTTP 方法
        url     覆盖配置中的 URL
        project 项目名，省略时从线程上下文自动读取
        **kwargs  透传给 requests.request（params / json / headers 等）

    返回 requests.Response；出错时异常会被 component_context 捕获并记录后重新抛出。

    示例：
        resp = primelog.call_external('user-service', params={'id': 123})
        resp = primelog.call_external('pay-gateway', method='POST',
                                       json={'amount': 100})
    """
    try:
        import requests as _requests
    except ImportError:
        raise ImportError("call_external 需要 requests 库：pip install requests")

    proj = project or _get_current_project()
    if not proj:
        raise ValueError("call_external 需要项目名：请传入 project= 或先调用 primelog.init()")

    comp_name = f"{proj}.{name}"
    spec = registry.get_spec(comp_name)
    if spec is None:
        raise ValueError(
            f"外部组件未注册: '{comp_name}'。"
            f"请先在 externals.json 中声明，或调用 primelog.register_external()。"
        )

    # 合并配置与运行时参数
    cfg = dict(spec.metadata)
    if method:
        cfg["method"] = method
    if url:
        cfg["url"] = url
    # kwargs 中的 params/json/data 等直接存入 cfg 供 _prepare_request 透传
    cfg.update(kwargs)

    req_kwargs = _prepare_request(cfg)

    with registry.component_context(comp_name):
        try:
            resp = _requests.request(**req_kwargs)
        except _requests.exceptions.Timeout:
            raise Exception("timeout")
        except _requests.exceptions.ConnectionError:
            raise Exception("network_error")
        # 4xx / 5xx → 映射为错误键，抛出让 component_context 记录
        if resp.status_code >= 400:
            raise Exception(_http_status_to_error(resp.status_code))
        return resp


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
    # 外部 API 追踪
    "call_external",
    "register_external",
]
