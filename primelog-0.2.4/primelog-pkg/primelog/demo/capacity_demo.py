#!/usr/bin/env python3
"""
PrimeLog 容量对比演示
======================
生成 10 万条随机事件，分别写入普通日志和 PrimeLog 格式，
比较两者文件大小，直观展示 PrimeLog 的对数压缩优势。
"""

import os
import sys
import random
import json
import glob
from datetime import datetime, timedelta

# 确保 primelog 已安装
try:
    import primelog
    from primelog.core.registry import registry   # 新增导入
except ImportError:
    print("错误: 请先安装 primelog (pip install primelog)")
    sys.exit(1)

# ========== 配置参数 ==========
NUM_EVENTS = 100000          # 事件数量
NUM_COMPONENTS = 100         # 组件数量
ERROR_TYPES = [
    "none", "timeout", "permission_denied", "file_not_found",
    "network_error", "disk_full", "auth_failed", "unknown", "execution_error"
]
LOG_DIR = "./demo_capacity"   # 日志输出目录
PROJECT_NAME = "capacity-demo"

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# ========== 1. 注册组件 ==========
print(f"正在注册 {NUM_COMPONENTS} 个虚拟组件...")
for i in range(NUM_COMPONENTS):
    comp_name = f"demo.component.{i}"
    # 将匿名函数注册为组件（仅用于占位，不会被实际调用）
    registry.register(name=comp_name, type_="demo", signature="dummy")(lambda: None)

# ========== 2. 生成随机事件 ==========
print(f"生成 {NUM_EVENTS} 条随机事件...")
events_data = []
start_time = datetime.now()
for _ in range(NUM_EVENTS):
    # 随机时间戳（平均每秒10个事件）
    timestamp = start_time + timedelta(seconds=random.expovariate(10))
    caller = f"demo.component.{random.randrange(NUM_COMPONENTS)}"
    callee = f"demo.component.{random.randrange(NUM_COMPONENTS)}"
    # 随机错误组合（0~3种错误，none 代表无错误）
    num_errors = random.choices([0, 1, 2, 3], weights=[0.7, 0.2, 0.07, 0.03])[0]
    if num_errors == 0:
        errors = ["none"]
    else:
        errors = random.sample(ERROR_TYPES[1:], k=num_errors)  # 排除 none
    events_data.append((timestamp, caller, callee, errors))

# ========== 3. 写入普通日志（JSON Lines 格式） ==========
print("写入普通日志...")
plain_log_path = os.path.join(LOG_DIR, "plain_log.jsonl")
with open(plain_log_path, "w", encoding="utf-8") as f:
    for ts, caller, callee, errors in events_data:
        record = {
            "timestamp": ts.isoformat(),
            "caller": caller,
            "callee": callee,
            "errors": errors
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
plain_size = os.path.getsize(plain_log_path)
print(f"普通日志大小: {plain_size:,} 字节")

# ========== 4. 使用 PrimeLog 记录并导出 ==========
print("初始化 PrimeLog...")
primelog.init(PROJECT_NAME, log_base=LOG_DIR)

print("记录事件到 PrimeLog...")
for ts, caller, callee, errors in events_data:
    # 注意：record_event 需要传入 components 参数（即 registry.components）
    primelog.record_event(caller, callee, errors, registry.components)   # 修正处

print("导出 PrimeLog 文件...")
primelog.export(project=PROJECT_NAME, output_dir=LOG_DIR)

# 查找生成的 PrimeLog 事件文件
primelog_files = glob.glob(os.path.join(LOG_DIR, PROJECT_NAME, "error_events_*.json"))
if not primelog_files:
    print("错误: 未找到 PrimeLog 导出文件")
    sys.exit(1)
primelog_file = primelog_files[0]
primelog_size = os.path.getsize(primelog_file)
print(f"PrimeLog 事件文件大小: {primelog_size:,} 字节")

# ========== 5. 对比容量 ==========
ratio = plain_size / primelog_size
print("\n" + "="*50)
print("容量对比结果")
print("="*50)
print(f"普通日志大小: {plain_size:,} 字节")
print(f"PrimeLog 大小: {primelog_size:,} 字节")
print(f"压缩比 (普通/PrimeLog): {ratio:.2f}")
print(f"PrimeLog 比普通日志节省空间: {(1 - 1/ratio)*100:.1f}%")
print("="*50)

# ========== 可选：展示文件内容示例 ==========
print("\n普通日志前两行示例:")
with open(plain_log_path, "r") as f:
    for i, line in enumerate(f):
        if i >= 2:
            break
        print(line.strip())

print("\nPrimeLog 文件开头 (前300字符):")
with open(primelog_file, "r") as f:
    content = f.read(300)
    print(content + "...")

print("\n演示完成。")
