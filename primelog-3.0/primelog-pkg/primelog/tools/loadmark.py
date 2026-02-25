#!/usr/bin/env python3
"""
loadmark.py — 管理 __loadmark__ 标记文件

职责：只负责在目录里放置或消除 __loadmark__ 标记。
与 register（打印章）、loader（扫描加载）完全独立。
"""

import os
from typing import List, Tuple


MARK_FILE = '__loadmark__'


def _apply(directory: str, remove: bool, recursive: bool, max_depth: int) -> List[Tuple[str, str]]:
    """
    核心逻辑：在目录树中添加或消除 __loadmark__。

    返回操作记录列表：[(动作, 路径), ...]
    动作为 'added' / 'removed' / 'exists' / 'not_found'
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return [('error', f"目录不存在: {directory}")]

    results = []

    def process_dir(path: str, depth: int):
        mark_path = os.path.join(path, MARK_FILE)

        if remove:
            if os.path.exists(mark_path):
                os.remove(mark_path)
                results.append(('removed', mark_path))
            else:
                results.append(('not_found', mark_path))
        else:
            if os.path.exists(mark_path):
                results.append(('exists', mark_path))
            else:
                open(mark_path, 'w').close()
                results.append(('added', mark_path))

        # 递归处理子目录
        if recursive and (max_depth < 0 or depth < max_depth):
            try:
                for entry in sorted(os.scandir(path), key=lambda e: e.name):
                    if entry.is_dir() and not entry.name.startswith('.') \
                            and entry.name != '__pycache__':
                        process_dir(entry.path, depth + 1)
            except PermissionError:
                results.append(('error', f"无权限访问: {path}"))

    process_dir(directory, depth=0)
    return results


def run(
    directory: str,
    remove: bool    = False,
    recursive: bool = False,
    max_depth: int  = -1,    # -1 表示无限深度
) -> None:
    """
    执行 loadmark 操作并打印结果。
    """
    results = _apply(directory, remove=remove, recursive=recursive, max_depth=max_depth)

    icons = {
        'added':     '✅ 添加',
        'removed':   '🗑  消除',
        'exists':    '⏭  已有',
        'not_found': '⚠️  不存在',
        'error':     '❌ 错误',
    }

    counts = {'added': 0, 'removed': 0, 'exists': 0, 'not_found': 0, 'error': 0}

    for action, path in results:
        print(f"  {icons.get(action, action)}  {path}")
        counts[action] = counts.get(action, 0) + 1

    print()
    if remove:
        print(f"消除完成：消除 {counts['removed']} 个，"
              f"不存在 {counts['not_found']} 个"
              + (f"，错误 {counts['error']} 个" if counts['error'] else ""))
    else:
        print(f"标记完成：新增 {counts['added']} 个，"
              f"已有 {counts['exists']} 个"
              + (f"，错误 {counts['error']} 个" if counts['error'] else ""))
