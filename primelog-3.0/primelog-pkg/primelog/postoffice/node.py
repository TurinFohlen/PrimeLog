"""
node.py — PostmareNode
信息素表维护、路由计算、定期老化。
纯内存逻辑，无网络细节。
"""

import time
import threading
import logging
from typing import Dict, Optional

logger = logging.getLogger('postmare.node')

# 信息素条目过期时间（秒）
PHEROMONE_MAX_AGE = 120
# 心跳广播间隔（秒）
BROADCAST_INTERVAL = 30
# 路由不可达时的占位值
INF = float('inf')


class PheromoneEntry:
    __slots__ = ('value', 'next_hop', 'timestamp')

    def __init__(self, value: float, next_hop: Optional[str], timestamp: float):
        self.value     = value
        self.next_hop  = next_hop
        self.timestamp = timestamp


class PostmareNode:
    """
    维护到主机的信息素表。

    外部接口：
        update(neighbor_fp, reported_value)  ← Transport 收到心跳后调用
        get_next_hop(target_fp)              ← Mailbag 发文件前调用
        get_pheromone_value(target_fp)       ← 广播时使用
        start() / stop()
    """

    def __init__(self,
                 self_fp: str,
                 host_fp: str,
                 broadcast_cb,          # callable(value: float)，让 Transport 广播
                 broadcast_interval: int = BROADCAST_INTERVAL):
        self.self_fp   = self_fp
        self.host_fp   = host_fp
        self._table: Dict[str, PheromoneEntry] = {}
        self._lock     = threading.Lock()
        self._running  = False
        self._broadcast_cb       = broadcast_cb
        self._broadcast_interval = broadcast_interval

        # 若本节点就是主机，成本固定为 0
        if self_fp == host_fp:
            self._table[host_fp] = PheromoneEntry(0.0, None, time.time())
            logger.info("本节点是主机，信息素初始化为 0")

    # ── 路由查询 ──────────────────────────────────────────────

    def get_next_hop(self, target_fp: str) -> Optional[str]:
        """返回到 target 的下一跳指纹，无路由返回 None。"""
        with self._lock:
            entry = self._table.get(target_fp)
        if entry and entry.value < INF:
            return entry.next_hop
        return None

    def get_pheromone_value(self, target_fp: str) -> float:
        with self._lock:
            entry = self._table.get(target_fp)
        return entry.value if entry else INF

    def has_route(self, target_fp: str) -> bool:
        return self.get_next_hop(target_fp) is not None

    # ── 路由更新（Transport 回调） ────────────────────────────

    def update(self, neighbor_fp: str, reported_value: float) -> bool:
        """
        收到邻居广播后调用。
        new_cost = reported_value + 1（跳数成本）。
        返回 True 表示路由有更新（可触发重新广播）。
        """
        if reported_value >= INF:
            return False

        new_cost = reported_value + 1.0
        target   = self.host_fp

        with self._lock:
            current = self._table.get(target)
            if current is None or new_cost < current.value:
                self._table[target] = PheromoneEntry(new_cost, neighbor_fp, time.time())
                logger.info(
                    f"路由更新 → {target[:8]}…  "
                    f"下一跳={neighbor_fp[:8]}…  成本={new_cost:.0f}"
                )
                return True
        return False

    # ── 老化（后台线程） ──────────────────────────────────────

    def _decay_loop(self):
        while self._running:
            time.sleep(PHEROMONE_MAX_AGE // 2)
            now = time.time()
            with self._lock:
                stale = [
                    fp for fp, e in self._table.items()
                    if fp != self.self_fp
                    and (now - e.timestamp) > PHEROMONE_MAX_AGE
                ]
                for fp in stale:
                    del self._table[fp]
                    logger.debug(f"老化删除路由 {fp[:8]}…")

    # ── 广播（后台线程） ─────────────────────────────────────

    def _broadcast_loop(self):
        # 启动时等一个间隔，让 Transport 先就绪
        time.sleep(self._broadcast_interval)
        while self._running:
            val = self.get_pheromone_value(self.host_fp)
            try:
                self._broadcast_cb(val)
            except Exception as e:
                logger.warning(f"广播回调异常: {e}")
            time.sleep(self._broadcast_interval)

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        self._running = True
        threading.Thread(target=self._decay_loop,     daemon=True, name='node-decay').start()
        threading.Thread(target=self._broadcast_loop, daemon=True, name='node-bcast').start()
        logger.info(f"PostmareNode 启动  self={self.self_fp[:8]}…  host={self.host_fp[:8]}…")

    def stop(self):
        self._running = False
