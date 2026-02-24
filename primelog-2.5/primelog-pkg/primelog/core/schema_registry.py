"""
primelog/core/schema_registry.py
──────────────────────────────────────────────────────────────────────────────
要素表（Schema）注册中心。

核心理念
--------
一个 Schema 就是一个"状态空间"：用户定义有哪些状态（维度值），每个状态映
射到唯一素数。记录事件时，多个同时成立的状态做素数乘积，取对数存为
log_value——与 error_log 完全相同的数学语义，但适用范围不再限于"错误"。

与 error_log 的关系
--------------------
- error_log 继续负责"组件调用 + 错误"这一具体场景，不受影响。
- schema_registry 提供通用平台，error_log 的 prime_map 本质上也是一个
  Schema（"error" schema），但两者代码不耦合，向后兼容零风险。

导出格式
--------
与 error_events_*.json 完全对齐（format_version 3.0），只增加两个字段：
  - metadata.schema      : schema 名称
  - metadata.dimensions  : 用户定义的维度列表（供文档和 UI 使用）
  - observers            : observer 名称列表（对应 observer_index）
  - subjects             : subject 名称列表（对应 subject_index）
  events_schema 改为 ["t", "observer_index", "subject_index", "log_value"]

这样 aggregate.py 无需修改即可合并 schema 事件文件。
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
#  素数工具（独立，不依赖 error_constants）
# ─────────────────────────────────────────────────────────────────────────────

def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def _next_prime_after(n: int) -> int:
    """返回严格大于 n 的最小素数。"""
    candidate = n + 1
    while not _is_prime(candidate):
        candidate += 1
    return candidate


# ─────────────────────────────────────────────────────────────────────────────
#  Schema 数据类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Schema:
    """
    一张要素表。

    Attributes
    ----------
    name        : 全局唯一标识符
    states      : {state_name: prime}，状态 → 素数映射
    dimensions  : 维度标签列表（文档用途，不影响存储逻辑）
    description : 人类可读描述
    """
    name:        str
    states:      Dict[str, int]        = field(default_factory=dict)
    dimensions:  List[str]             = field(default_factory=list)
    description: str                   = ""
    _lock:       threading.Lock        = field(default_factory=threading.Lock,
                                               repr=False, compare=False)

    # ── 素数管理 ──────────────────────────────────────────────────────────

    def _max_prime_used(self) -> int:
        return max(self.states.values(), default=1)

    def ensure_state(self, state: str) -> int:
        """
        确保 state 存在于映射中。若不存在，自动分配下一个素数并注册。
        返回对应素数。
        """
        with self._lock:
            if state in self.states:
                return self.states[state]
            prime = _next_prime_after(self._max_prime_used())
            self.states[state] = prime
            return prime

    def log_value(self, state_list: List[str]) -> float:
        """
        将状态列表编码为 log_value。
        空列表或仅含 "none" → 0.0（无状态，乘法单位元 ln(1)=0）。
        """
        filtered = [s for s in state_list if s != "none"]
        if not filtered:
            return 0.0
        product = 1
        for s in filtered:
            product *= self.ensure_state(s)
        return math.log(product)

    def decode(self, log_value: float) -> List[str]:
        """将 log_value 解码回状态列表。"""
        if log_value <= 0:
            return ["none"]
        composite = round(math.exp(log_value))
        result = []
        remaining = composite
        for name, prime in sorted(self.states.items(), key=lambda x: x[1]):
            if prime <= 1:
                continue
            if remaining % prime == 0:
                result.append(name)
                while remaining % prime == 0:
                    remaining //= prime
        return result or ["unknown"]

    def to_dict(self) -> dict:
        """序列化为 JSON 可用的 dict。"""
        return {
            "name":        self.name,
            "states":      dict(self.states),
            "dimensions":  list(self.dimensions),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Schema":
        return cls(
            name        = d["name"],
            states      = d.get("states", {}),
            dimensions  = d.get("dimensions", []),
            description = d.get("description", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  事件存储（per-project, per-schema）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _SchemaStore:
    """单个（project, schema）组合的运行时存储。"""
    events:        List[Tuple[int, int, int, float]]      = field(default_factory=list)
    # (t_index, observer_index, subject_index, log_value)
    timed_events:  List[Tuple[str, int, int, float]]      = field(default_factory=list)
    # (iso_timestamp, observer_index, subject_index, log_value)
    observers:     Dict[str, int]                          = field(default_factory=dict)
    subjects:      Dict[str, int]                          = field(default_factory=dict)
    timestamps:    List[str]                               = field(default_factory=list)
    event_counter: int                                     = 0
    export_dir:    str                                     = "."

    def _obs_idx(self, name: str) -> int:
        if name not in self.observers:
            self.observers[name] = len(self.observers)
        return self.observers[name]

    def _subj_idx(self, name: str) -> int:
        if name not in self.subjects:
            self.subjects[name] = len(self.subjects)
        return self.subjects[name]

    def record(self, observer: str, subject: str, log_val: float) -> None:
        obs_i  = self._obs_idx(observer or "__root__")
        subj_i = self._subj_idx(subject)
        ts     = datetime.now().isoformat()
        t      = self.event_counter
        self.event_counter += 1
        self.timestamps.append(ts)
        self.events.append((t, obs_i, subj_i, log_val))
        self.timed_events.append((ts, obs_i, subj_i, log_val))


# ─────────────────────────────────────────────────────────────────────────────
#  全局注册中心
# ─────────────────────────────────────────────────────────────────────────────

class SchemaRegistry:
    """
    全局单例：管理所有 Schema 定义和每个（project, schema）的事件存储。
    """

    def __init__(self):
        self._schemas:  Dict[str, Schema]          = {}   # name → Schema
        self._stores:   Dict[str, _SchemaStore]    = {}   # "{project}:{schema}" → store
        self._lock      = threading.Lock()
        self._thread_local = threading.local()

    # ── Schema 注册 ───────────────────────────────────────────────────────

    def define(
        self,
        name:        str,
        states:      Dict[str, int] = None,
        dimensions:  List[str]      = None,
        description: str            = "",
    ) -> Schema:
        """
        注册（或覆盖）一个 Schema。幂等：同名 Schema 已存在时合并 states，
        不会抹掉现有的事件数据。
        """
        with self._lock:
            if name in self._schemas:
                existing = self._schemas[name]
                # 合并新增 states（不覆盖已有映射）
                if states:
                    for k, v in states.items():
                        if k not in existing.states:
                            existing.states[k] = v
                return existing

            schema = Schema(
                name        = name,
                states      = dict(states or {}),
                dimensions  = list(dimensions or []),
                description = description,
            )
            self._schemas[name] = schema
            return schema

    def get(self, name: str) -> Schema:
        """获取 Schema，不存在时抛 KeyError。"""
        if name not in self._schemas:
            raise KeyError(
                f"Schema '{name}' 未注册。请先调用 primelog.define_schema('{name}', ...)"
            )
        return self._schemas[name]

    def list_schemas(self) -> List[str]:
        return list(self._schemas.keys())

    # ── 项目绑定（与 error_log 保持同样的线程本地模型）────────────────────

    def bind_project(self, project: str, export_dir: str = ".") -> None:
        """绑定当前线程到指定项目。"""
        self._thread_local.project = project
        # 确保 store 初始化时带上 export_dir
        # 各 schema 的 store 在 record_state 时懒创建

    def _current_project(self) -> str:
        return getattr(self._thread_local, "project", "__global__")

    def _store_key(self, project: str, schema_name: str) -> str:
        return f"{project}:{schema_name}"

    def _get_store(self, project: str, schema_name: str,
                   export_dir: str = ".") -> _SchemaStore:
        key = self._store_key(project, schema_name)
        with self._lock:
            if key not in self._stores:
                self._stores[key] = _SchemaStore(export_dir=export_dir)
            return self._stores[key]

    def set_export_dir(self, project: str, schema_name: str,
                       export_dir: str) -> None:
        key = self._store_key(project, schema_name)
        with self._lock:
            if key in self._stores:
                self._stores[key].export_dir = export_dir

    # ── 事件记录 ─────────────────────────────────────────────────────────

    def record_state(
        self,
        schema_name: str,
        subject:     str,
        states:      List[str],
        observer:    str = "",
        project:     str = "",
        export_dir:  str = ".",
    ) -> None:
        """
        记录一次状态观测事件。

        Parameters
        ----------
        schema_name : 要素表名称
        subject     : 被观测对象（如服务器 ID、订单 ID）
        states      : 当前状态列表（可多个同时成立）
        observer    : 观测者（可选，默认 "__root__"）
        project     : 项目名，默认使用线程绑定项目
        export_dir  : 导出目录（首次创建 store 时使用）
        """
        schema = self.get(schema_name)
        log_val = schema.log_value(states)
        proj    = project or self._current_project()
        store   = self._get_store(proj, schema_name, export_dir)

        with self._lock:
            store.record(observer, subject, log_val)

    # ── 导出 ──────────────────────────────────────────────────────────────

    def export_schema(
        self,
        schema_name: str,
        project:     str = "",
        filepath:    Optional[str] = None,
    ) -> Optional[str]:
        """
        将指定 schema 的事件导出为 JSON（格式与 error_events 对齐）。
        返回写入的文件路径，无事件时返回 None。
        """
        proj    = project or self._current_project()
        key     = self._store_key(proj, schema_name)
        schema  = self.get(schema_name)

        with self._lock:
            if key not in self._stores:
                return None
            store = self._stores[key]
            if not store.events:
                return None
            # 快照（避免导出期间写入竞态）
            events       = list(store.events)
            timed_events = list(store.timed_events)
            observers    = dict(store.observers)
            subjects     = dict(store.subjects)
            export_dir   = store.export_dir

        # 构建时间戳序列（相对秒数）
        if timed_events:
            start_ts_str = timed_events[0][0]
            start_ts     = datetime.fromisoformat(start_ts_str)
            timestamps   = [
                round((datetime.fromisoformat(ts) - start_ts).total_seconds(), 9)
                for ts, *_ in timed_events
            ]
        else:
            start_ts_str = ""
            timestamps   = []

        # 反转索引表用于导出
        obs_names  = _invert(observers)
        subj_names = _invert(subjects)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        if filepath is None:
            fname    = f"{schema_name}_events_{now_str}.json"
            filepath = os.path.join(export_dir, fname)

        payload = {
            "metadata": {
                "schema":          schema_name,
                "dimensions":      schema.dimensions,
                "description":     schema.description,
                "timestamp":       now_str,
                "n_events":        len(events),
                "format_version":  "3.0",
                "start_timestamp": start_ts_str,
            },
            "prime_map":     schema.states,
            "observers":     obs_names,
            "subjects":      subj_names,
            "timestamps":    timestamps,
            "events":        [[t, oi, si, lv] for t, oi, si, lv in events],
            "events_schema": ["t", "observer_index", "subject_index", "log_value"],
        }

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"[schema] {schema_name} → {filepath}", file=sys.stderr)
        return filepath

    def export_all_schemas(
        self,
        project:    str = "",
        output_dir: str = "",
    ) -> List[str]:
        """
        导出当前项目所有已记录 schema 的事件文件。
        返回写入的文件路径列表。
        """
        proj    = project or self._current_project()
        prefix  = f"{proj}:"
        written = []

        with self._lock:
            keys = [k for k in self._stores if k.startswith(prefix)]

        for key in keys:
            schema_name = key[len(prefix):]
            try:
                schema = self.get(schema_name)
            except KeyError:
                continue
            out_dir = output_dir or self._stores[key].export_dir
            path = self.export_schema(schema_name, project=proj,
                                      filepath=os.path.join(
                                          out_dir,
                                          f"{schema_name}_events_"
                                          f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                      ))
            if path:
                written.append(path)

        return written

    # ── 加载 Schema 定义文件（可选：从 schemas/ 目录加载 JSON）────────────

    def load_schema_file(self, filepath: str) -> Schema:
        """
        从 JSON 文件加载 Schema 定义。
        文件格式与 Schema.to_dict() 对应。
        """
        with open(filepath, encoding="utf-8") as f:
            d = json.load(f)
        return self.define(
            name        = d["name"],
            states      = d.get("states", {}),
            dimensions  = d.get("dimensions", []),
            description = d.get("description", ""),
        )

    def save_schema_file(self, schema_name: str, filepath: str) -> None:
        """将 Schema 定义保存到 JSON 文件（供共享/版本控制）。"""
        schema = self.get(schema_name)
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(schema.to_dict(), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _invert(d: Dict[str, int]) -> List[str]:
    """将 {name: idx} 反转为按 idx 排序的名称列表。"""
    result = [""] * len(d)
    for name, idx in d.items():
        result[idx] = name
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  全局单例
# ─────────────────────────────────────────────────────────────────────────────

_schema_registry = SchemaRegistry()
