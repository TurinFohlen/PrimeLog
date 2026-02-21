#!/usr/bin/env python3
"""
register_file.py — 给任意 .py 文件打上 PrimeLog 印章

用法：
    primelog register <文件.py> <type> <项目名> [signature]

效果：
    1. 在文件顶部插入 import primelog（如果没有）
    2. 在第一个 class 或 def 上方插入 @primelog.component(...)
    3. 原文件备份为 <文件.py>.bak
"""

import re
import os
import shutil
from typing import Tuple, Optional


def _has_primelog_import(lines: list) -> bool:
    """检查文件是否已有 import primelog"""
    for line in lines:
        stripped = line.strip()
        if stripped in ('import primelog', 'from primelog import component'):
            return True
    return False


def _has_primelog_decorator(lines: list) -> bool:
    """检查文件是否已有 @primelog.component"""
    for line in lines:
        if '@primelog.component' in line or '@primelog.register' in line:
            return True
    return False


def _find_first_class_or_def(lines: list) -> Optional[int]:
    """
    找到第一个顶层 class 或 def 的行号（0-indexed）。
    跳过缩进的（只找顶层），跳过注释和字符串。
    """
    in_docstring = False
    docstring_char = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 处理多行字符串
        if not in_docstring:
            for q in ('"""', "'''"):
                if stripped.startswith(q):
                    if stripped.count(q) == 1 or (stripped.count(q) == 2 and len(stripped) == 3):
                        in_docstring = True
                        docstring_char = q
                        break
            if in_docstring:
                continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue

        # 跳过注释行
        if stripped.startswith('#'):
            continue

        # 找顶层 class 或 def（不缩进）
        if re.match(r'^(class|def)\s+\w+', line):
            return i

    return None


def _find_import_insert_point(lines: list) -> int:
    """
    找到适合插入 import primelog 的位置：
    在所有现有 import 语句之后，在第一个 class/def 之前。
    """
    last_import_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            last_import_line = i

    if last_import_line >= 0:
        return last_import_line + 1

    # 没有任何 import，找到文件头部注释/docstring 之后
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
            return i

    return 0


def stamp(
    filepath: str,
    type_: str,
    project: str,
    signature: str = "",
    backup: bool = True,
) -> Tuple[bool, str]:
    """
    给文件打上 PrimeLog 印章。

    返回 (success, message)
    """
    if not os.path.isfile(filepath):
        return False, f"文件不存在: {filepath}"

    if not filepath.endswith('.py'):
        return False, f"只支持 .py 文件: {filepath}"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines(keepends=True)

    # 检查是否已经有印章
    if _has_primelog_decorator(lines):
        return False, f"文件已有 @primelog.component 装饰器，跳过: {filepath}"

    # 推导组件名：project.文件名（去掉路径和 .py）
    basename   = os.path.splitext(os.path.basename(filepath))[0]
    comp_name  = f"{project}.{basename}"

    # 构造装饰器字符串
    if signature:
        decorator = f'@primelog.component("{comp_name}", type_="{type_}", signature="{signature}")\n'
    else:
        decorator = f'@primelog.component("{comp_name}", type_="{type_}")\n'

    # 备份原文件
    if backup:
        bak_path = filepath + '.bak'
        shutil.copy2(filepath, bak_path)

    # ── 步骤1：插入 import primelog ──────────────────
    if not _has_primelog_import(lines):
        insert_at = _find_import_insert_point(lines)
        lines.insert(insert_at, 'import primelog\n')
        # 插入后行号偏移 +1
        offset = 1
    else:
        offset = 0

    # ── 步骤2：找第一个 class/def，插入装饰器 ────────
    first_def = _find_first_class_or_def(lines)

    if first_def is not None:
        # 在 class/def 上方插入装饰器
        lines.insert(first_def, decorator)
    else:
        # 没有 class/def，追加到文件末尾
        if lines and not lines[-1].endswith('\n'):
            lines.append('\n')
        lines.append('\n')
        lines.append(decorator)

    # ── 写回文件 ────────────────────────────────────
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    msg = f'✅ 已标记: {filepath}\n   组件名: {comp_name}\n   类型:   {type_}'
    if signature:
        msg += f'\n   签名:   {signature}'
    if backup:
        msg += f'\n   备份:   {filepath}.bak'

    return True, msg


def stamp_multiple(
    filepaths: list,
    type_: str,
    project: str,
    signature: str = "",
) -> None:
    """批量打印章"""
    success = 0
    for fp in filepaths:
        ok, msg = stamp(fp, type_=type_, project=project, signature=signature)
        print(msg)
        if ok:
            success += 1
    print(f"\n共处理 {len(filepaths)} 个文件，成功 {success} 个")


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 4:
        print("用法: python register_file.py <文件.py> <type> <项目名> [signature]")
        sys.exit(1)
    filepath  = sys.argv[1]
    type_     = sys.argv[2]
    project   = sys.argv[3]
    signature = sys.argv[4] if len(sys.argv) > 4 else ""
    ok, msg = stamp(filepath, type_=type_, project=project, signature=signature)
    print(msg)
    sys.exit(0 if ok else 1)
