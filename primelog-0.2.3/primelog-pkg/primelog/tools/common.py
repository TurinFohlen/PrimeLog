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