#!/usr/bin/env python3
"""
全库引入者·智能版 —— 自动扫描所有包含 __loadmark__ 标记的目录。
"""

import os
import sys
import importlib.util
from pathlib import Path
from collections import defaultdict

def scan_and_import(root_override: str = None):
    """
    自动发现当前根目录下所有包含 __loadmark__ 文件的子目录，
    并递归导入其中的所有 .py 文件（除 __init__.py 外）。
    """
    # 支持从 core/ 子目录或根目录运行，统一以项目根目录为扫描基准
    root_dir = Path(root_override).resolve() if root_override else Path.cwd()
    if (root_dir / "__loadmark__").exists() or not any((root_dir.parent / d).is_dir() and (root_dir.parent / d / "__loadmark__").exists() for d in ["."] if False):
        # 检查是否在子目录（core/），若父目录有 __loadmark__ 子目录则用父目录
        parent = root_dir.parent
        if any((parent / d).is_dir() and (parent / d / "__loadmark__").exists() for d in os.listdir(parent) if (parent / d).is_dir()):
            root_dir = parent
    packages = []

    # 遍历根目录下的直接子目录
    for entry in root_dir.iterdir():
        if entry.is_dir():
            # 检查是否存在标记文件
            mark_file = entry / "__loadmark__"
            if mark_file.exists():
                packages.append(entry.name)

    if not packages:
        print("⚠️ 未找到任何包含 __loadmark__ 的目录，没有包被扫描。")
        return []

    imported = []  # 存储 (depth, module_name)

    for pkg in packages:
        pkg_dir = root_dir / pkg
        # 递归扫描该包下的所有 .py 文件
        for py_file in pkg_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            try:
                # 计算相对于包目录的路径
                rel_path = py_file.relative_to(pkg_dir)
                depth = len(rel_path.parts) - 1

                # 动态导入模块
                sub_module = ".".join(rel_path.with_suffix('').parts)
                module_name = f"{pkg}.{sub_module}"
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    sys.modules[module_name] = module
                    imported.append((depth, module_name))
            except Exception as e:
                print(f"⚠️ 导入失败 {py_file.name}: {e}")

    return imported


def build_tree(module_list):
    """将模块名列表转换为嵌套字典树"""
    tree = lambda: defaultdict(tree)
    root = tree()
    for _, mod in module_list:
        parts = mod.split(".")
        node = root
        for part in parts:
            node = node[part]
    return root


def print_tree(node, prefix="", name=""):
    """递归打印树状结构"""
    if name:
        print(prefix + "└── " + name)
        prefix += "        "
    children = list(node.keys())
    for child in children:
        print_tree(node[child], prefix, child)


# ========== 执行自动扫描导入 ==========
loaded_modules = scan_and_import()
print(f"✅ 全库智能加载完成，已注册 {len(loaded_modules)} 个组件\n")

# 构建并打印树
tree = build_tree(loaded_modules)
print_tree(tree)