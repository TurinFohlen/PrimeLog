#!/usr/bin/env python3
"""
全库引入者·智能版 —— 自动扫描所有包含 __loadmark__ 标记的目录（递归查找）。
每个含标记的目录被视为一个独立组件包的根，其下的所有 .py 文件（不含 __init__.py）
都会以该目录的相对路径为前缀被动态导入。
"""

import os
import sys
import importlib.util
from pathlib import Path
from collections import defaultdict

def scan_and_import(root_override: str = None):
    """
    递归扫描根目录下所有包含 __loadmark__ 文件的子目录，
    将每个这样的目录作为组件包根，并导入其中的所有 .py 文件。
    """
    # 确定根目录（兼容从 core/ 子目录运行）
    root_dir = Path(root_override).resolve() if root_override else Path.cwd()
    # 如果当前目录是 core/ 且父目录下有带 __loadmark__ 的子目录，则退到父目录作为根
    if (root_dir.name == 'core' and root_dir.parent.exists()):
        parent = root_dir.parent
        for child in parent.iterdir():
            if child.is_dir() and (child / "__loadmark__").exists():
                root_dir = parent
                break

    print(f"🔍 扫描根目录: {root_dir}")

    # 递归查找所有包含 __loadmark__ 的目录
    mark_dirs = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "__loadmark__" in filenames:
            mark_dirs.append(Path(dirpath))

    if not mark_dirs:
        print("⚠️ 未找到任何包含 __loadmark__ 的目录，没有包被扫描。")
        return []

    imported = []  # 存储 (depth, module_name)

    for mark_dir in mark_dirs:
        # 计算相对于根目录的路径作为模块名前缀
        try:
            rel_path = mark_dir.relative_to(root_dir)
        except ValueError:
            continue
        prefix = ".".join(rel_path.parts) if rel_path != Path('.') else ""

        # 递归遍历该标记目录下的所有 .py 文件
        for py_file in mark_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            try:
                rel_file = py_file.relative_to(mark_dir)
                sub_module = ".".join(rel_file.with_suffix('').parts)
                module_name = f"{prefix}.{sub_module}" if prefix else sub_module
                depth = len(rel_file.parts) - 1

                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    sys.modules[module_name] = module
                    imported.append((depth, module_name))
            except Exception as e:
                print(f"⚠️ 导入失败 {py_file}: {e}")

    return imported


def build_tree(module_list):
    tree = lambda: defaultdict(tree)
    root = tree()
    for _, mod in module_list:
        parts = mod.split(".")
        node = root
        for part in parts:
            node = node[part]
    return root


def print_tree(node, prefix="", name=""):
    if name:
        print(prefix + "└── " + name)
        prefix += "        "
    for child in list(node.keys()):
        print_tree(node[child], prefix, child)


# ========== 执行自动扫描导入 ==========
if __name__ == "__main__":
    loaded_modules = scan_and_import()
    print(f"✅ 全库智能加载完成，已注册 {len(loaded_modules)} 个组件\n")
    tree = build_tree(loaded_modules)
    print_tree(tree)