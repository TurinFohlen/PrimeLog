# primelog/tools/common.py
"""工具通用函数：日志查找、路径解析等"""

import os
import glob
from datetime import datetime
from typing import Optional

def find_latest_log(log_dir: str, project: Optional[str] = None, pattern: str = "error_events_*.json") -> Optional[str]:
    """
    在指定日志目录（可带项目子目录）下查找最新的匹配文件。
    如果指定 project，则在 log_dir/project 下查找；否则直接在 log_dir 下查找。
    """
    if project:
        log_dir = os.path.join(log_dir, project)
    pattern_path = os.path.join(log_dir, pattern)
    files = glob.glob(pattern_path)
    if not files:
        return None
    # 按修改时间排序取最新
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[0]

def resolve_log_dir(base_dir: str, project: Optional[str] = None) -> str:
    """返回实际的日志目录路径（如果指定项目则拼接）"""
    if project:
        return os.path.join(base_dir, project)
    return base_dir

def ensure_log_dir_exists(path: str) -> None:
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)

# ── 格式兼容层：v2.0 对数格式 → composite 整数 ──────────────────
import math

def _banker_round(x: float) -> int:
    """
    四舍六入五成双（银行家舍入）。
    标准 round() 在 Python 3 已是银行家舍入，直接复用即可。
    此函数显式命名，方便各 tool import 时语义清晰。
    """
    return round(x)


def get_composite(event: list) -> int:
    """
    从事件列表安全读取 composite 整数值。

    兼容两种格式：
      v1.x  event[3] = composite（整数）  → 直接返回
      v2.0  event[3] = log_value（浮点）  → exp 求逆 + 银行家舍入还原

    判断依据：event[3] 是 float 且 < 1e15 认为是对数值；
              int 或超大值认为是旧格式 composite。
    """
    raw = event[3]
    if isinstance(raw, float):
        return _banker_round(math.exp(raw))
    return int(raw)


def decode_event(event: list, prime_map: dict) -> list:
    """
    从事件列表直接解码出错误类型列表（兼容 v1.x / v2.0）。
    省去各 tool 自己 import error_log 的麻烦。
    """
    from primelog.core.error_log import decode_errors
    return decode_errors(get_composite(event), prime_map)
