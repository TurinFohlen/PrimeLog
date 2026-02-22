#!/usr/bin/env python3
"""
error_log.py - 素数编码错误日志系统(含相对时间戳 v3.0)
==========================================================
将运行时组件调用事件编码为结构化张量数据,
支持导出为 JSON 和 Wolfram Language 格式,
以便后续在 Mathematica 中进行张量分析.

数学原理:
  - 每种错误类型映射到唯一素数 ("none"->1)
  - 一次调用的复合值 = 所有错误素数之积 (唯一分解定理保证可逆)
  - 对数变换后: log(p1*p2*...) = log(p1)+log(p2)+..., 便于线性分析
  - 最终构成三维张量 E[caller_idx][callee_idx][t] = log(composite)

v3.0 改进:
  - 时间戳改为相对起始时间的秒数(浮点数), 便于数学运算
  - 增加 start_timestamp / startTimestamp 记录绝对起始时间
  - 大幅缩减文件大小
"""

import math
import json
import threading
import atexit
import sys
import os
from datetime import datetime
from functools import reduce
import operator
from typing import Dict, List, Optional, Tuple, Any


# ------------------------------------------------------------
# 1. 素数映射表(可在运行时通过 register_error_type 扩展)
# ------------------------------------------------------------

prime_map: Dict[str, int] = {
    "none":             1,   # 乘法单位元, 代表无错误
    "timeout":          2,
    "permission_denied":3,
    "file_not_found":   5,
    "network_error":    7,
    "disk_full":        11,
    "auth_failed":      13,
    "unknown":          17,  # 未识别异常的默认映射
    "execution_error":  19,  # 命令执行失败(非零返回码)
}

# 用于扩展 prime_map 时自动分配下一个可用素数
_next_prime_candidates = [23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83]


def register_error_type(error_name: str) -> int:
    """
    动态注册新的错误类型, 自动分配下一个未使用素数.
    返回分配的素数.
    """
    if error_name in prime_map:
        return prime_map[error_name]
    if not _next_prime_candidates:
        # 备用: 直接用 sympy 或手动维护更大列表
        raise RuntimeError("素数候选列表已耗尽, 请扩展 _next_prime_candidates")
    p = _next_prime_candidates.pop(0)
    prime_map[error_name] = p
    return p


# ------------------------------------------------------------
# 2. 异常类型 -> 错误名称 映射
# ------------------------------------------------------------

# 内置异常类到错误名称的映射表
_exception_map: Dict[type, str] = {
    TimeoutError:           "timeout",
    PermissionError:        "permission_denied",
    FileNotFoundError:      "file_not_found",
    ConnectionError:        "network_error",
    ConnectionResetError:   "network_error",
    ConnectionRefusedError: "network_error",
    OSError:                "disk_full",      # 磁盘满常以 OSError 出现
    MemoryError:            "disk_full",
    RuntimeError:           "execution_error",  # rish 命令执行失败
}


def exception_to_error(exc: Exception) -> str:
    """
    将异常实例映射为错误类型字符串.
    优先精确匹配, 再做 MRO 遍历, 最后返回 "unknown".
    """
    for exc_type, error_name in _exception_map.items():
        if isinstance(exc, exc_type):
            return error_name
    # 尝试用异常类名推导(例如 AuthError -> "auth_failed" 如果存在)
    class_name = type(exc).__name__.lower()
    for key in prime_map:
        if key != "none" and key != "unknown" and key in class_name:
            return key
    return "unknown"


# ------------------------------------------------------------
# 3. 核心数学函数
# ------------------------------------------------------------

def composite_value(error_set: List[str]) -> int:
    """
    计算一次调用的复合错误值: 所有错误类型对应素数的乘积.
    error_set = ["none"] 时返回 1 (乘法单位元).
    """
    return reduce(operator.mul, (prime_map.get(e, prime_map["unknown"]) for e in error_set), 1)


def log_composite_value(error_set: List[str]) -> float:
    """
    计算复合值的自然对数.
    无错误时返回 0.0 (log(1) = 0).
    """
    val = composite_value(error_set)
    return math.log(val) if val > 1 else 0.0


def decode_errors(composite: int) -> List[str]:
    """
    逆向解码: 通过因式分解从复合值还原错误类型列表.
    基于算术基本定理(唯一分解定理), 解码是唯一确定的.
    """
    if composite <= 1:
        return ["none"]
    result = []
    remaining = composite
    for err, p in prime_map.items():
        if p > 1 and remaining % p == 0:
            result.append(err)
            while remaining % p == 0:
                remaining //= p
    return result if result else ["unknown"]


# ------------------------------------------------------------
# 4. 全局事件存储(多项目线程安全)
# ------------------------------------------------------------
# 架构说明:
#   _project_store[key] = {
#       'events':        List[Tuple],   # (t, caller_idx, callee_idx, error_set)
#       'timed_events':  List[Tuple],   # (timestamp, caller_idx, callee_idx, error_set)
#       'export_dir':    str,
#       'event_counter': int,
#   }
#   _thread_local.project_key 存储当前线程绑定的项目 key (线程私有)
#   record_event / export_* 通过 _get_project_store() 路由到对应项目
#
# 向后兼容:
#   _events / _timed_events / export_dir / _event_counter 仍作为
#   "无项目"模式的 fallback, 行为与旧版完全一致.

_project_store: Dict[str, dict] = {}       # project_key -> 项目状态
_thread_local  = threading.local()         # .project_key (线程私有)
_store_lock    = threading.Lock()          # 保护 _project_store 结构修改

# fallback (无项目模式, 向后兼容)
_events: List[Tuple[int, int, int, List[str]]] = []
_timed_events: List[Tuple[str, int, int, List[str]]] = []
_event_counter = 0
_lock = threading.Lock()

# 是否启用日志(可动态切换)
enabled: bool = True

# 导出目录(默认为当前目录, 无项目模式使用)
export_dir: str = "."


def _init_project(key: str, proj_export_dir: str = ".") -> None:
    """初始化一个项目的存储槽(幂等)"""
    with _store_lock:
        if key not in _project_store:
            _project_store[key] = {
                'events':        [],
                'timed_events':  [],
                'export_dir':    proj_export_dir,
                'event_counter': 0,
            }
        elif proj_export_dir != ".":
            _project_store[key]['export_dir'] = proj_export_dir


def _bind_thread(key: str) -> None:
    """绑定当前线程到指定项目 key"""
    _thread_local.project_key = key


def _get_project_store() -> dict:
    """
    返回当前线程绑定项目的 store dict.
    若无绑定, 返回 fallback (使用模块级全局变量的伪 store).
    """
    key = getattr(_thread_local, 'project_key', None)
    if key and key in _project_store:
        return _project_store[key]
    # fallback: 返回引用模块全局变量的视图(向后兼容)
    return None   # None 表示使用 fallback 路径


def log_to_composite(log_value: float) -> int:
    """
    对数值 -> 素数乘积(四舍五入取整).
    浮点误差通过取整消除, 结果精确还原原始整数乘积.

    示例:
        log_to_composite(math.log(2 * 5)) == 10
    """
    return round(math.exp(log_value))


def decode_from_log(log_value: float) -> List[str]:
    """
    对数值 -> 错误类型列表.
    先调用 log_to_composite 还原乘积, 再进行素数因数分解.

    示例:
        decode_from_log(math.log(2 * 5))  # ["timeout", "file_not_found"]
    """
    composite = log_to_composite(log_value)
    return decode_errors(composite)


def _get_component_index(name: Optional[str], components: Dict) -> int:
    """
    根据组件名获取其在注册中心中的排序索引.
    若组件不存在, 返回 -1.
    """
    if name is None:
        return -1
    sorted_names = sorted(components.keys(),
                          key=lambda n: components[n].registration_order)
    try:
        return sorted_names.index(name)
    except ValueError:
        return -1


def record_event(
    caller_name: Optional[str],
    callee_name: str,
    error_set: List[str],
    components: Dict
) -> None:
    """
    记录一次组件调用事件.
    自动路由到当前线程绑定项目的 store; 无绑定时写 fallback 全局列表.
    """
    global _event_counter

    if not enabled:
        return
    if caller_name is None or caller_name == callee_name:
        return

    try:
        caller_idx = _get_component_index(caller_name, components)
        callee_idx = _get_component_index(callee_name, components)
        if caller_idx == -1 or callee_idx == -1:
            return

        for err in error_set:
            if err not in prime_map:
                register_error_type(err)

        timestamp = datetime.now().isoformat()
        store = _get_project_store()

        if store is not None:
            with _store_lock:
                t = store['event_counter']
                store['event_counter'] += 1
                store['events'].append((t, caller_idx, callee_idx, list(error_set)))
                store['timed_events'].append((timestamp, caller_idx, callee_idx, list(error_set)))
        else:
            with _lock:
                t = _event_counter
                _event_counter += 1
                _events.append((t, caller_idx, callee_idx, list(error_set)))
                _timed_events.append((timestamp, caller_idx, callee_idx, list(error_set)))

    except Exception as e:
        # 日志记录失败不影响主流程
        print(f"[error_log] 记录事件失败: {e}", file=sys.stderr)


# ------------------------------------------------------------
# 5. 导出函数(拆分版: A 与 events 独立成文件)
# ------------------------------------------------------------

def _get_adjacency_list(registry_instance) -> Dict[str, Any]:
    """从注册中心获取邻接矩阵数据(带权)"""
    try:
        return registry_instance.get_adjacency_matrix()
    except Exception:
        return {
            "nodes": [],
            "csr_format": {"data": [], "indices": [], "row_ptrs": [0]},
            "relation_prime_map": {}
        }


# -- JSON 格式 -------------------------------------------------

def export_adjacency_json(registry_instance, filepath: Optional[str] = None) -> str:
    """【独立文件①】仅导出静态依赖矩阵 A 到 JSON(带权)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if filepath is None:
        filepath = os.path.join((_get_project_store() or {}).get("export_dir", export_dir), f"adjacency_matrix_{timestamp}.json")

    adj = _get_adjacency_list(registry_instance)
    nodes = adj.get("nodes", [])
    csr = adj.get("csr_format", {})
    row_ptrs = csr.get("row_ptrs", [0])
    indices = csr.get("indices", [])
    data = csr.get("data", [])
    rel_map = adj.get("relation_prime_map", {})

    triples = []
    for i, (rp_start, rp_end) in enumerate(zip(row_ptrs[:-1], row_ptrs[1:])):
        for k in range(rp_start, rp_end):
            triples.append([i, indices[k], data[k]])

    payload = {
        "metadata": {
            "timestamp": timestamp,
            "n_components": len(nodes),
            "format_version": "2.0",
            "description": "静态依赖矩阵(带权, 权值为关系类型素数)"
        },
        "nodes": nodes,
        "relation_prime_map": rel_map,
        "adjacency_csr": csr,
        "adjacency_triples": triples,
        "triples_schema": ["row_index", "col_index", "value"]
    }

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[error_log] 邻接矩阵 JSON -> {filepath}", file=sys.stderr)
    return filepath


def export_events_json(filepath: Optional[str] = None) -> str:
    """
    【独立文件②】导出错误事件列表(v3.0, 时间戳为相对秒数).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    store = _get_project_store()
    _ev  = store['events']       if store else _events
    _tev = store['timed_events'] if store else _timed_events
    _dir = store['export_dir']   if store else export_dir
    if filepath is None:
        filepath = os.path.join(_dir, f"error_events_{timestamp}.json")

    if not _tev:
        start_timestamp = ""
        timestamps = []
    else:
        start_ts_str = _tev[0][0]
        start_ts = datetime.fromisoformat(start_ts_str)
        start_timestamp = start_ts_str
        timestamps = []
        for ts_str, _, _, _ in _tev:
            ts = datetime.fromisoformat(ts_str)
            offset = (ts - start_ts).total_seconds()
            timestamps.append(offset)

    events_export = [
        [t, ci, cj, log_composite_value(err_set)]
        for t, ci, cj, err_set in _ev
    ]

    payload = {
        "metadata": {
            "timestamp":      timestamp,
            "n_events":       len(_ev),
            "format_version": "3.0",
            "description":    "运行时错误事件列表(相对时间戳, 起始时间为 start_timestamp)",
            "start_timestamp": start_timestamp,
        },
        "prime_map":     prime_map,
        "timestamps":    timestamps,          # 浮点数列表
        "events":        events_export,
        "events_schema": ["t", "caller_index", "callee_index", "log_value"]
    }

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[error_log] 错误事件 JSON -> {filepath}", file=sys.stderr)
    return filepath


# -- Wolfram Language 格式 -------------------------------------

def export_adjacency_wl(registry_instance, filepath: Optional[str] = None) -> str:
    """【独立文件③】仅导出静态依赖矩阵 A 到 Wolfram Language (.wl)(带权)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if filepath is None:
        filepath = os.path.join((_get_project_store() or {}).get("export_dir", export_dir), f"adjacency_matrix_{timestamp}.wl")

    adj = _get_adjacency_list(registry_instance)
    nodes = adj.get("nodes", [])
    n = len(nodes)
    csr = adj.get("csr_format", {})
    row_ptrs = csr.get("row_ptrs", [0])
    indices = csr.get("indices", [])
    data = csr.get("data", [])
    rel_map = adj.get("relation_prime_map", {})

    lines = []
    lines.append("(* ============================================================")
    lines.append("   静态依赖矩阵(带权) - 由 error_log.py 自动生成")
    lines.append(f"   生成时间: {timestamp}    组件数量: {n}")
    lines.append("   使用方式: Get[\"adjacency_matrix.wl\"]")
    lines.append("   ============================================================ *)")
    lines.append("")
    nodes_wl = "{" + ", ".join(f'"{nd}"' for nd in nodes) + "}"
    lines.append(f"nodes = {nodes_wl};  (* 组件名列表, 索引从1开始 *)")
    lines.append(f"n = {n};             (* 组件总数 *)")
    lines.append("")

    # 输出关系映射
    rel_entries = ", ".join(f'"{k}"->{v}' for k, v in rel_map.items())
    lines.append(f"relationPrimeMap = <|{rel_entries}|>;")
    lines.append("")

    # 构建 SparseArray 规则
    sparse_rules = []
    for i, (rp_start, rp_end) in enumerate(zip(row_ptrs[:-1], row_ptrs[1:])):
        for k in range(rp_start, rp_end):
            j = indices[k]
            prime = data[k]
            sparse_rules.append(f"{{{i+1},{j+1}}}->{prime}")

    if sparse_rules:
        rules_wl = "{" + ", ".join(sparse_rules) + "}"
        lines.append(f"staticDepA = SparseArray[{rules_wl}, {{{n},{n}}}];")
    else:
        lines.append(f"staticDepA = SparseArray[{{}}, {{{n},{n}}}];")
    lines.append("")
    lines.append("(* 查看矩阵: MatrixForm[Normal[staticDepA]] *)")
    lines.append("(* 找出所有依赖对及其类型: Select[ArrayRules[staticDepA], #[[2]]!=0 &] *)")

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[error_log] 邻接矩阵 WL  -> {filepath}", file=sys.stderr)
    return filepath


def export_events_wl(registry_instance, filepath: Optional[str] = None, include_errors: bool = True) -> str:
    """
    导出错误事件列表到 Wolfram Language (.wl) 文件(v3.0, 时间戳为相对秒数).

    参数:
        registry_instance: 注册中心实例
        filepath: 输出文件路径(若为 None 则自动生成)
        include_errors: 若为 True, events 中包含明文错误列表; 否则只包含 log_value (紧凑版)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    store_w  = _get_project_store()
    _ev_w    = store_w['events']       if store_w else _events
    _tev_w   = store_w['timed_events'] if store_w else _timed_events
    _dir_w   = store_w['export_dir']   if store_w else export_dir

    if filepath is None:
        if include_errors:
            filename = f"error_events_{timestamp}.wl"
        else:
            filename = f"error_events_compact_{timestamp}.wl"
        filepath = os.path.join(_dir_w, filename)

    adj     = _get_adjacency_list(registry_instance)
    n       = len(adj.get("nodes", []))
    total_t = len(_ev_w)

    # 计算相对时间戳
    if not _tev_w:
        start_ts_str = ""
        timestamps = []
    else:
        start_ts_str = _tev_w[0][0]
        start_ts = datetime.fromisoformat(start_ts_str)
        timestamps = []
        for ts_str, _, _, _ in _tev_w:
            ts = datetime.fromisoformat(ts_str)
            offset = (ts - start_ts).total_seconds()
            timestamps.append(offset)

    lines = []
    lines.append("(* ============================================================")
    lines.append("   错误事件列表(素数编码) - 由 error_log.py 自动生成")
    lines.append(f"   生成时间: {timestamp}    事件数量: {total_t}")
    lines.append(f"   格式版本: 3.0 (相对时间戳, 起始时间见 startTimestamp)")
    if include_errors:
        lines.append("   文件版本: 可读版(含明文错误列表)")
    else:
        lines.append("   文件版本: 紧凑版(仅含 log_value, 需自行解码)")
    lines.append("   使用方式: Get[\"" + os.path.basename(filepath) + "\"]")
    lines.append("   ============================================================ *)")
    lines.append("")

    pm_entries = ", ".join(f'"{k}"->{v}' for k, v in prime_map.items())
    lines.append(f"primeMap = <|{pm_entries}|>;")
    lines.append("")

    # 起始时间
    lines.append(f'startTimestamp = "{start_ts_str}";  (* 第一个事件的绝对时间 *)')
    lines.append("")

    # 导出时间戳列表(相对秒数)
    timestamps_wl = "{" + ", ".join(f"{t:.6f}" for t in timestamps) + "}"
    lines.append(f"timestamps = {timestamps_wl};  (* 与 events 对应的时间偏移(秒) *)")
    lines.append("")

    if include_errors:
        lines.append("(* 事件格式: {t, caller_index, callee_index, errors_list, log_value} *)")
        lines.append("(* 恢复乘积: Round[Exp[logValue]]  恢复错误: 对乘积做素数因数分解 *)")
    else:
        lines.append("(* 事件格式: {t, caller_index, callee_index, log_value} *)")
        lines.append("(* 解码错误: decodeErrors[logValue, primeMap]  *)")

    if _ev_w:
        event_lines = []
        for t, ci, cj, err_set in _ev_w:
            lv  = log_composite_value(err_set)
            if include_errors:
                errs_wl = "{" + ", ".join(f'"{e}"' for e in err_set) + "}"
                event_lines.append(f"  {{{t+1},{ci+1},{cj+1},{errs_wl},{lv:.10f}}}")
            else:
                event_lines.append(f"  {{{t+1},{ci+1},{cj+1},{lv:.10f}}}")
        events_wl = "{\n" + ",\n".join(event_lines) + "\n}"
    else:
        events_wl = "{}"
    lines.append(f"events = {events_wl};")
    lines.append(f"totalT = {max(total_t, 1)};")
    lines.append("")

    # 为紧凑版提供解码函数
    if not include_errors:
        lines.append("(* 辅助解码函数(基于 primeMap 和 logValue) *)")
        lines.append("decodeErrors[logValue_, primeMap_] := Module[{composite = Round[Exp[logValue]]},")
        lines.append("  If[composite == 1, Return[{\"none\"}]];")
        lines.append("  Reap[")
        lines.append("    Do[")
        lines.append("      If[Mod[composite, p] == 0,")
        lines.append("        Sow[name];")
        lines.append("        While[Mod[composite, p] == 0, composite /= p];")
        lines.append("      ],")
        lines.append("      {name, p}, {p, Values[primeMap]}, {name, Keys[primeMap]}")
        lines.append("    ]")
        lines.append("  ][[2,1]] /. {}. {\"unknown\"}")
        lines.append("];")
        lines.append("")

    lines.append("(* 三维稀疏对数错误张量 errorTensor[[caller, callee, t]] *)")
    lines.append(f"(* 需先加载 adjacency_matrix.wl 以获得 n *)")
    if _ev_w:
        tensor_rules = []
        for t, ci, cj, err_set in _ev_w:
            lv = log_composite_value(err_set)
            if lv > 0:
                tensor_rules.append(f"  {{{ci+1},{cj+1},{t+1}}}->{lv:.10f}")
        if tensor_rules:
            tr_wl = "{\n" + ",\n".join(tensor_rules) + "\n}"
            lines.append(f"errorTensor = SparseArray[{tr_wl}, {{{n},{n},{total_t}}}];")
        else:
            lines.append(f"errorTensor = SparseArray[{{}}, {{{n},{n},{total_t}}}];")
    else:
        lines.append(f"errorTensor = SparseArray[{{}}, {{{n},{n},1}}];")
    lines.append("")
    lines.append("(* --- 后续分析示例 --- *)")
    lines.append("(* 可以将 timestamps 转换为 AbsoluteTime 用于时域分析 *)")
    lines.append("(* absoluteTimes = AbsoluteTime[startTimestamp] + timestamps; *)")
    lines.append("(* receivedError = Table[Total[Normal[errorTensor][[All,j,All]],2],{j,n}]; *)")
    lines.append("(* producedError = Table[Total[Normal[errorTensor][[i,All,All]],2],{i,n}]; *)")

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[error_log] 错误事件 WL  -> {filepath}", file=sys.stderr)
    return filepath


# -- 主导出入口 -------------------------------------------------

def export_error_log(registry_instance=None) -> None:
    """
    主导出函数: 同时生成 4 个独立文件(v3.0 相对时间戳):
        adjacency_matrix_<ts>.json          -- 静态依赖矩阵 A (JSON)
        error_events_<ts>.json               -- 错误事件列表 (v3.0 JSON)
        adjacency_matrix_<ts>.wl             -- 静态依赖矩阵 A (Wolfram)
        error_events_<ts>.wl                  -- 错误事件列表 (Wolfram, 可读版, v3.0)
        error_events_compact_<ts>.wl          -- 错误事件列表 (紧凑版, Wolfram, v3.0)

    由 atexit / 信号处理器自动调用, 也可手动调用.
    """
    if registry_instance is None:
        try:
            from primelog.core.registry import registry as _reg
            registry_instance = _reg
        except ImportError:
            print("[error_log] 无法获取 registry 实例, 跳过导出", file=sys.stderr)
            return

    _chk = _get_project_store()
    _ev_chk = _chk['events'] if _chk else _events
    if not _ev_chk:
        print("[error_log] 无事件记录, 跳过导出", file=sys.stderr)
        return

    print(f"\n[error_log] 开始导出 {len(_ev_chk)} 条事件(共 4 个文件, v3.0 相对时间戳)...", file=sys.stderr)
    export_adjacency_json(registry_instance)
    export_events_json()
    export_adjacency_wl(registry_instance)
    #export_events_wl(registry_instance, include_errors=True)   # 可读版
    export_events_wl(registry_instance, include_errors=False)  # 紧凑版
    print("[error_log] 全部导出完成 ✅", file=sys.stderr)


def get_stats() -> Dict[str, Any]:
    """返回当前记录统计信息, 便于调试"""
    with _lock:
        error_counts: Dict[str, int] = {}
        for _, _, _, err_set in _events:
            for e in err_set:
                error_counts[e] = error_counts.get(e, 0) + 1
        return {
            "total_events": len(_events),
            "error_distribution": error_counts,
            "enabled": enabled,
        }