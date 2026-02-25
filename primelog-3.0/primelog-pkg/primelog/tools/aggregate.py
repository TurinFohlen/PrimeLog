#!/usr/bin/env python3
"""
aggregate.py — PrimeLog 多节点日志聚合工具
==========================================
将多个节点导出的 error_events_*.json / adjacency_matrix_*.json
合并为单份全局文件，格式与单节点完全一致，可直接交给分析工具使用。

处理流程
--------
1. 发现文件   ── 递归扫描目录 or 接受显式文件对
2. 节点标识   ── 按 ip（或 node-id）给组件名加前缀，消除命名冲突
3. 组件合并   ── 生成全局 nodes 列表，建立 (node, old_idx) → global_idx 映射
4. 事件合并   ── 相对时间 + start_timestamp → 绝对 UTC epoch，排序后
                 重新生成相对时间戳序列，caller/callee 换成全局索引
5. 邻接矩阵   ── triples 换全局索引，去重时取权值乘积（保持素数语义）
6. 输出       ── error_events_global.json / adjacency_matrix_global.json

用法
----
# 指定根目录，自动找每个子目录最新的一对文件
python aggregate.py --dir /logs --node-ip 192.168.1.10

# 直接指定文件（多节点）
python aggregate.py \\
    --node 192.168.1.10 logs/node1/error_events_20260224.json logs/node1/adjacency_matrix_20260224.json \\
    --node 192.168.1.20 logs/node2/error_events_20260224.json logs/node2/adjacency_matrix_20260224.json \\
    --global-name production

# 自动扫描模式（节点 ip 从目录名推断）
python aggregate.py --dir /mnt/postoffice/incoming --global-name nightly --output-dir /logs/global
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
#  数据类
# ─────────────────────────────────────────────────────────────────────────────

class NodeData:
    """单个节点的原始日志数据。"""

    def __init__(self, node_id: str,
                 events_path: Path, adj_path: Path):
        self.node_id    = node_id          # 节点标识（ip 或目录名）
        self.events_path = events_path
        self.adj_path    = adj_path

        self.ev  = json.loads(events_path.read_text(encoding="utf-8"))
        self.adj = json.loads(adj_path.read_text(encoding="utf-8"))

        # 解析 start_timestamp → UTC epoch（秒）
        raw_ts = self.ev["metadata"].get("start_timestamp", "")
        try:
            dt = datetime.fromisoformat(raw_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            self.start_epoch: float = dt.timestamp()
        except Exception:
            self.start_epoch = 0.0

    @property
    def nodes(self) -> List[str]:
        return self.adj.get("nodes", [])

    @property
    def events(self) -> List[List]:
        return self.ev.get("events", [])

    @property
    def timestamps(self) -> List[float]:
        return self.ev.get("timestamps", [])

    @property
    def triples(self) -> List[List]:
        return self.adj.get("adjacency_triples", [])

    @property
    def prime_map(self) -> Dict[str, int]:
        return self.ev.get("prime_map", {})

    @property
    def relation_prime_map(self) -> Dict[str, int]:
        return self.adj.get("relation_prime_map", {})


# ─────────────────────────────────────────────────────────────────────────────
#  文件发现
# ─────────────────────────────────────────────────────────────────────────────

def _latest_pair(directory: Path) -> Optional[Tuple[Path, Path]]:
    """
    在 directory 中找最新的 (error_events_*.json, adjacency_matrix_*.json) 对。
    按时间戳字符串降序排，取第一个。
    """
    ev_files  = sorted(directory.glob("error_events_*.json"),     reverse=True)
    adj_files = sorted(directory.glob("adjacency_matrix_*.json"), reverse=True)
    if not ev_files or not adj_files:
        return None
    # 尝试配对同时间戳
    for ev in ev_files:
        ts = _extract_ts(ev.name)
        for adj in adj_files:
            if _extract_ts(adj.name) == ts:
                return ev, adj
    # fallback：各取最新
    return ev_files[0], adj_files[0]


def _extract_ts(filename: str) -> str:
    """从文件名提取时间戳部分，如 error_events_20260224_050934.json → 20260224_050934"""
    m = re.search(r"(\d{8}_\d{6})", filename)
    return m.group(1) if m else ""


def discover_nodes(root: Path) -> List[Tuple[str, Path, Path]]:
    """
    递归扫描 root，在每个含日志文件的子目录中找最新一对文件。
    返回 [(node_id, events_path, adj_path), ...]
    node_id 优先取目录名（适合以 IP 命名的 incoming 子目录）。
    """
    results = []
    # 先试 root 本身
    pair = _latest_pair(root)
    if pair:
        results.append((root.name, pair[0], pair[1]))
    # 再扫一级子目录
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        pair = _latest_pair(subdir)
        if pair:
            results.append((subdir.name, pair[0], pair[1]))
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  合并逻辑
# ─────────────────────────────────────────────────────────────────────────────

def _prefix(node_id: str, name: str) -> str:
    """将组件名加节点前缀：192.168.1.10::my-project.api.gateway"""
    return f"{node_id}::{name}"


def aggregate(nodes: List[NodeData], global_name: str = "global") -> Tuple[dict, dict]:
    """
    核心聚合函数。
    返回 (error_events_global, adjacency_matrix_global)，格式与单节点完全一致。
    """

    # ── Step 1: 合并 prime_map（取并集，同名 key 必须素数一致）─────────────
    unified_prime_map: Dict[str, int] = {}
    for nd in nodes:
        for err_type, prime in nd.prime_map.items():
            if err_type in unified_prime_map and unified_prime_map[err_type] != prime:
                _warn(f"节点 {nd.node_id}: 错误类型 '{err_type}' 素数冲突 "
                      f"({unified_prime_map[err_type]} vs {prime})，保留已有值")
            else:
                unified_prime_map[err_type] = prime

    # ── Step 2: 合并 relation_prime_map（同理）────────────────────────────
    unified_rel_map: Dict[str, int] = {}
    for nd in nodes:
        for rel, prime in nd.relation_prime_map.items():
            unified_rel_map.setdefault(rel, prime)

    # ── Step 3: 构建全局组件列表，建立索引映射 ───────────────────────────
    global_nodes: List[str] = []
    node_index_map: Dict[Tuple[str, int], int] = {}   # (node_id, old_idx) → global_idx

    for nd in nodes:
        for old_idx, comp_name in enumerate(nd.nodes):
            prefixed = _prefix(nd.node_id, comp_name)
            if prefixed not in global_nodes:
                global_nodes.append(prefixed)
            g_idx = global_nodes.index(prefixed)
            node_index_map[(nd.node_id, old_idx)] = g_idx

    n_global = len(global_nodes)

    # ── Step 4: 合并事件（相对时间 → 绝对 epoch → 全局排序）──────────────
    abs_events: List[Tuple[float, int, int, float]] = []
    # (abs_epoch, global_caller, global_callee, log_value)

    for nd in nodes:
        timestamps = nd.timestamps
        for ev in nd.events:
            # schema: [t_index, caller_index, callee_index, log_value]
            t_idx, caller_old, callee_old, log_val = (
                int(ev[0]), int(ev[1]), int(ev[2]), float(ev[3])
            )
            rel_t = timestamps[t_idx] if t_idx < len(timestamps) else 0.0
            abs_t = nd.start_epoch + rel_t

            g_caller = node_index_map.get((nd.node_id, caller_old))
            g_callee = node_index_map.get((nd.node_id, callee_old))
            if g_caller is None or g_callee is None:
                _warn(f"节点 {nd.node_id}: 事件索引越界 "
                      f"caller={caller_old} callee={callee_old}，跳过")
                continue

            abs_events.append((abs_t, g_caller, g_callee, log_val))

    # 按绝对时间排序
    abs_events.sort(key=lambda x: x[0])

    # 重建相对时间戳序列（以最早事件为 t=0）
    if abs_events:
        t0 = abs_events[0][0]
        global_start_ts = datetime.fromtimestamp(t0, tz=timezone.utc).isoformat()
    else:
        t0 = 0.0
        global_start_ts = datetime.now(tz=timezone.utc).isoformat()

    global_timestamps: List[float] = []
    global_events: List[List] = []

    for i, (abs_t, g_caller, g_callee, log_val) in enumerate(abs_events):
        global_timestamps.append(round(abs_t - t0, 9))
        global_events.append([i, g_caller, g_callee, log_val])

    # ── Step 5: 合并邻接矩阵（triples 换全局索引，去重取乘积）─────────────
    # 相同 (caller, callee) 边：关系值做乘积（保持素数语义，多关系类型叠加）
    edge_map: Dict[Tuple[int, int], int] = {}

    for nd in nodes:
        for triple in nd.triples:
            old_r, old_c, val = int(triple[0]), int(triple[1]), int(triple[2])
            g_r = node_index_map.get((nd.node_id, old_r))
            g_c = node_index_map.get((nd.node_id, old_c))
            if g_r is None or g_c is None:
                continue
            key = (g_r, g_c)
            if key in edge_map:
                # 合并：取 LCM（避免重复素数因子指数叠加），保留已有语义
                edge_map[key] = _lcm(edge_map[key], val)
            else:
                edge_map[key] = val

    global_triples = [[r, c, v] for (r, c), v in sorted(edge_map.items())]

    # 重建 CSR（与单节点格式一致）
    csr = _build_csr(global_triples, n_global)

    # ── Step 6: 构建输出 dict ────────────────────────────────────────────
    now_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

    error_events_global = {
        "metadata": {
            "timestamp":       now_str,
            "global_name":     global_name,
            "n_events":        len(global_events),
            "n_nodes":         len(nodes),
            "node_ids":        [nd.node_id for nd in nodes],
            "format_version":  "3.0",
            "description":     "全局聚合事件列表（多节点合并，绝对时间对齐）",
            "start_timestamp": global_start_ts,
            "aggregated_at":   datetime.now(tz=timezone.utc).isoformat(),
        },
        "prime_map":    unified_prime_map,
        "timestamps":   global_timestamps,
        "events_schema": ["t", "caller_index", "callee_index", "log_value"],
        "events":       global_events,
        "nodes":        global_nodes,   # 冗余字段，方便直接读取
    }

    adjacency_matrix_global = {
        "metadata": {
            "timestamp":      now_str,
            "global_name":    global_name,
            "n_components":   n_global,
            "n_nodes":        len(nodes),
            "node_ids":       [nd.node_id for nd in nodes],
            "format_version": "2.0",
            "description":    "全局聚合静态依赖矩阵（多节点合并）",
        },
        "nodes":              global_nodes,
        "relation_prime_map": unified_rel_map,
        "adjacency_csr":      csr,
        "adjacency_triples":  global_triples,
        "triples_schema":     ["row_index", "col_index", "value"],
    }

    return error_events_global, adjacency_matrix_global


# ─────────────────────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _lcm(a: int, b: int) -> int:
    """最小公倍数（用于合并关系边时保持素数语义）。"""
    return a * b // math.gcd(a, b)


def _build_csr(triples: List[List], n: int) -> dict:
    """从 triples 构建 CSR（与单节点格式一致）。"""
    data, indices, row_ptrs = [], [], [0]
    by_row: Dict[int, List] = {}
    for r, c, v in triples:
        by_row.setdefault(r, []).append((c, v))

    for row in range(n):
        for c, v in sorted(by_row.get(row, [])):
            data.append(v)
            indices.append(c)
        row_ptrs.append(len(data))

    return {"data": data, "indices": indices, "row_ptrs": row_ptrs}


def _warn(msg: str) -> None:
    print(f"[aggregate] ⚠  {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[aggregate] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
#  写入输出
# ─────────────────────────────────────────────────────────────────────────────

def write_output(ev_global: dict, adj_global: dict,
                 output_dir: Path, global_name: str) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    now_str = ev_global["metadata"]["timestamp"]

    ev_path  = output_dir / f"error_events_{global_name}_{now_str}.json"
    adj_path = output_dir / f"adjacency_matrix_{global_name}_{now_str}.json"

    ev_path.write_text(
        json.dumps(ev_global,  ensure_ascii=False, indent=2), encoding="utf-8")
    adj_path.write_text(
        json.dumps(adj_global, ensure_ascii=False, indent=2), encoding="utf-8")

    return ev_path, adj_path


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aggregate",
        description="PrimeLog 多节点日志聚合工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例
----
# 自动扫描目录（子目录名即节点 id）
  python aggregate.py --dir /mnt/incoming --global-name nightly

# 手动指定节点（可重复 --node）
  python aggregate.py \\
      --node 192.168.1.10 ev_node1.json adj_node1.json \\
      --node 192.168.1.20 ev_node2.json adj_node2.json \\
      --global-name prod --output-dir ./logs/global

# 只有一个根目录，自己就是节点
  python aggregate.py --dir ./logs --node-ip 10.0.0.1
""")

    p.add_argument("--dir", metavar="DIR",
                   help="根目录，自动递归发现各节点最新文件对")
    p.add_argument("--node-ip", metavar="IP",
                   help="配合 --dir 使用：当 --dir 本身就是单节点目录时，指定其 IP")
    p.add_argument("--node", metavar=("NODE_ID", "EVENTS", "ADJ"),
                   nargs=3, action="append", dest="nodes",
                   help="手动指定一个节点（可重复）：node_id events.json adj.json")
    p.add_argument("--global-name", default="global",
                   help="输出文件名中缀，默认 global")
    p.add_argument("--output-dir", default=".",
                   help="输出目录，默认当前目录")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印发现的文件和统计，不写入")
    return p


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # ── 收集节点 ──────────────────────────────────────────────────────────
    raw_nodes: List[Tuple[str, Path, Path]] = []   # (node_id, ev_path, adj_path)

    if args.dir:
        root = Path(args.dir)
        if not root.is_dir():
            parser.error(f"--dir 不是目录: {root}")
        discovered = discover_nodes(root)
        if not discovered:
            parser.error(f"在 {root} 中未找到任何日志文件对")
        # 如果只发现了 root 本身（单目录），用 --node-ip 覆盖节点 id
        if len(discovered) == 1 and args.node_ip:
            discovered[0] = (args.node_ip, discovered[0][1], discovered[0][2])
        raw_nodes.extend(discovered)

    if args.nodes:
        for node_id, ev_str, adj_str in args.nodes:
            ev_p  = Path(ev_str)
            adj_p = Path(adj_str)
            if not ev_p.exists():
                parser.error(f"找不到事件文件: {ev_p}")
            if not adj_p.exists():
                parser.error(f"找不到邻接矩阵文件: {adj_p}")
            raw_nodes.append((node_id, ev_p, adj_p))

    if not raw_nodes:
        parser.error("请指定 --dir 或至少一个 --node")

    # ── 打印发现的节点 ─────────────────────────────────────────────────────
    _info(f"发现 {len(raw_nodes)} 个节点：")
    for node_id, ev_p, adj_p in raw_nodes:
        _info(f"  [{node_id}]  {ev_p.name}  +  {adj_p.name}")

    if args.dry_run:
        _info("--dry-run 模式，退出（不写入文件）")
        return

    # ── 加载数据 ───────────────────────────────────────────────────────────
    node_data = []
    for node_id, ev_p, adj_p in raw_nodes:
        try:
            nd = NodeData(node_id, ev_p, adj_p)
            node_data.append(nd)
            _info(f"  [{node_id}] 加载完成：{len(nd.events)} 事件，"
                  f"{len(nd.nodes)} 组件，start={nd.ev['metadata'].get('start_timestamp','?')}")
        except Exception as e:
            parser.error(f"加载节点 {node_id} 失败: {e}")

    # ── 聚合 ───────────────────────────────────────────────────────────────
    _info("开始聚合…")
    ev_global, adj_global = aggregate(node_data, global_name=args.global_name)

    n_ev  = ev_global["metadata"]["n_events"]
    n_comp = adj_global["metadata"]["n_components"]
    _info(f"聚合完成：{n_comp} 个全局组件，{n_ev} 个事件")

    # ── 写入 ───────────────────────────────────────────────────────────────
    out_dir = Path(args.output_dir)
    ev_path, adj_path = write_output(ev_global, adj_global, out_dir, args.global_name)
    _info(f"已写入：")
    _info(f"  {ev_path}")
    _info(f"  {adj_path}")


if __name__ == "__main__":
    main()
