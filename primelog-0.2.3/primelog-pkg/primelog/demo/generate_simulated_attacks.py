#!/usr/bin/env python3
"""
生成模拟的网络攻击错误事件日志，用于测试傅里叶分析。
模拟场景：
- 三个组件：firewall (防护墙), web_server, database
- 攻击每隔 10 秒触发一次（可调整），持续 5 分钟
- 攻击期间，web_server 会向 database 发起调用，并随机产生 network_error 或 timeout
- 攻击间隔内也可能有正常调用（错误为 none）
"""

import json
import math
import random
from datetime import datetime, timedelta

# 配置
OUTPUT_FILE = "simulated_attacks.json"
DURATION = 300          # 总时长（秒），5分钟
ATTACK_INTERVAL = 10    # 攻击间隔（秒）
EVENTS_PER_SECOND = 2   # 平均每秒事件数（攻击和非攻击时都可能有）
ERROR_PROB_ATTACK = 0.7 # 攻击时产生错误的概率
ERROR_PROB_NORMAL = 0.1 # 非攻击时产生错误的概率

# 组件列表（按注册顺序）
nodes = ["firewall", "web_server", "database"]

# 错误类型素数映射
prime_map = {
    "none": 1,
    "timeout": 2,
    "network_error": 3,
    "database_error": 5,
    "permission_denied": 7,
    "unknown": 11
}

def composite_value(errors):
    """计算错误集合对应的复合值（素数乘积）"""
    val = 1
    for e in errors:
        val *= prime_map.get(e, prime_map["unknown"])
    return val

def generate_timestamps(start, end, rate):
    """生成泊松分布的时间戳（平均每秒 rate 个事件）"""
    timestamps = []
    current = start
    while current < end:
        # 泊松过程：间隔服从指数分布
        interval = random.expovariate(rate)
        current += timedelta(seconds=interval)
        if current < end:
            timestamps.append(current)
    return timestamps

def main():
    start_time = datetime.now().replace(microsecond=0)  # 用当前时间作为开始
    end_time = start_time + timedelta(seconds=DURATION)

    # 生成所有时间戳（混合攻击与非攻击）
    all_timestamps = generate_timestamps(start_time, end_time, EVENTS_PER_SECOND)
    all_timestamps.sort()

    events = []
    timestamps_iso = []

    # 定义几种可能的调用路径
    call_paths = [
        (1, 2),  # web_server -> database
        (0, 1),  # firewall -> web_server
        (1, 1),  # web_server 自调用（忽略，因为record_event会过滤自调用，但为简化我们保留）
    ]

    for t, ts in enumerate(all_timestamps):
        # 随机选择一个调用路径
        caller, callee = random.choice([p for p in call_paths if p[0] != p[1]])  # 避免自调用

        # 判断当前时间是否在攻击窗口内
        # 攻击每 ATTACK_INTERVAL 秒持续一小段时间（比如 2 秒）
        attack_active = False
        seconds_since_start = (ts - start_time).total_seconds()
        if int(seconds_since_start) % ATTACK_INTERVAL < 2:  # 攻击持续2秒
            attack_active = True

        # 决定错误类型
        if attack_active:
            # 攻击期间：大概率产生错误
            if random.random() < ERROR_PROB_ATTACK:
                # 随机选择错误类型
                err_type = random.choice(["timeout", "network_error", "database_error"])
                errors = [err_type]
            else:
                errors = ["none"]
        else:
            # 正常期间：小概率产生错误
            if random.random() < ERROR_PROB_NORMAL:
                err_type = random.choice(["timeout", "permission_denied"])
                errors = [err_type]
            else:
                errors = ["none"]

        composite = composite_value(errors)
        log_value = math.log(composite) if composite > 1 else 0.0

        events.append([t, caller, callee, composite, log_value])
        timestamps_iso.append(ts.isoformat())

    # 构建输出数据
    output = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "n_events": len(events),
            "format_version": "1.0",
            "description": "模拟网络攻击错误事件"
        },
        "prime_map": prime_map,
        "timestamps": timestamps_iso,
        "events": events,
        "events_schema": ["t", "caller_index", "callee_index", "composite_value", "log_value"]
    }

    # 保存到文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 已生成模拟日志文件: {OUTPUT_FILE}")
    print(f"   总事件数: {len(events)}")
    print(f"   时间范围: {start_time} 到 {end_time}")

if __name__ == "__main__":
    main()