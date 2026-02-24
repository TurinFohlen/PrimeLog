"""
tests/test_schema_registry.py
──────────────────────────────
Schema 要素表注册中心的完整测试。
全程不需要文件系统（导出测试用 tmp_path）。
"""
import json, math, threading
from pathlib import Path
import pytest

from primelog.core.schema_registry import (
    Schema, SchemaRegistry, _schema_registry,
    _is_prime, _next_prime_after, _invert,
)
import primelog


# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════
class TestPrimeUtils:
    def test_is_prime(self):
        assert _is_prime(2) and _is_prime(3) and _is_prime(5) and _is_prime(7)
        assert not _is_prime(1) and not _is_prime(4) and not _is_prime(9)

    def test_next_prime_after(self):
        assert _next_prime_after(2)  == 3
        assert _next_prime_after(10) == 11
        assert _next_prime_after(12) == 13

    def test_invert(self):
        d = {"a": 0, "b": 1, "c": 2}
        assert _invert(d) == ["a", "b", "c"]

    def test_invert_empty(self):
        assert _invert({}) == []


# ═══════════════════════════════════════════════════════════════
#  Schema 类
# ═══════════════════════════════════════════════════════════════
class TestSchema:
    def _make(self):
        return Schema(
            name   = "cpu_load",
            states = {"low": 2, "medium": 3, "high": 5, "critical": 7},
        )

    # ── 素数管理 ──────────────────────────────────────────────
    def test_ensure_state_existing(self):
        s = self._make()
        assert s.ensure_state("low") == 2

    def test_ensure_state_auto_alloc(self):
        s = self._make()
        prime = s.ensure_state("overload")  # 7 已用，下一个应是 11
        assert prime == 11
        assert s.states["overload"] == 11

    def test_ensure_state_idempotent(self):
        s = self._make()
        p1 = s.ensure_state("new_state")
        p2 = s.ensure_state("new_state")
        assert p1 == p2

    # ── 编码 ──────────────────────────────────────────────────
    def test_log_value_none_state(self):
        s = self._make()
        assert s.log_value([]) == 0.0
        assert s.log_value(["none"]) == 0.0

    def test_log_value_single(self):
        s = self._make()
        assert s.log_value(["low"]) == pytest.approx(math.log(2))

    def test_log_value_multi(self):
        s = self._make()
        # low(2) * high(5) = 10 → ln(10)
        assert s.log_value(["low", "high"]) == pytest.approx(math.log(10))

    def test_log_value_order_independent(self):
        s = self._make()
        assert s.log_value(["low", "high"]) == s.log_value(["high", "low"])

    # ── 解码 ──────────────────────────────────────────────────
    def test_decode_zero(self):
        s = self._make()
        assert s.decode(0.0) == ["none"]

    def test_decode_single(self):
        s = self._make()
        lv = s.log_value(["medium"])
        assert s.decode(lv) == ["medium"]

    def test_decode_multi(self):
        s = self._make()
        lv = s.log_value(["low", "critical"])
        decoded = s.decode(lv)
        assert set(decoded) == {"low", "critical"}

    def test_encode_decode_roundtrip(self):
        s = self._make()
        for combo in [["low"], ["high"], ["medium", "critical"], ["low","medium","high"]]:
            lv = s.log_value(combo)
            assert set(s.decode(lv)) == set(combo)

    # ── 序列化 ────────────────────────────────────────────────
    def test_to_dict(self):
        s = self._make()
        d = s.to_dict()
        assert d["name"]   == "cpu_load"
        assert d["states"]["low"] == 2

    def test_from_dict_roundtrip(self):
        s    = self._make()
        s.dimensions  = ["server_id"]
        s.description = "test"
        s2   = Schema.from_dict(s.to_dict())
        assert s2.name   == s.name
        assert s2.states == s.states
        assert s2.dimensions == ["server_id"]


# ═══════════════════════════════════════════════════════════════
#  SchemaRegistry
# ═══════════════════════════════════════════════════════════════
class TestSchemaRegistry:
    """每个测试用独立的 registry 实例，避免状态污染。"""

    def _reg(self):
        return SchemaRegistry()

    # ── define ────────────────────────────────────────────────
    def test_define_basic(self):
        r = self._reg()
        s = r.define("temp", states={"cold":2,"warm":3,"hot":5})
        assert s.name == "temp"
        assert s.states["cold"] == 2

    def test_define_idempotent(self):
        r  = self._reg()
        s1 = r.define("temp", states={"cold":2})
        s2 = r.define("temp", states={"cold":2})
        assert s1 is s2

    def test_define_merges_new_states(self):
        r = self._reg()
        r.define("temp", states={"cold":2})
        r.define("temp", states={"hot":5})   # 新增状态
        s = r.get("temp")
        assert "cold" in s.states
        assert "hot"  in s.states

    def test_define_does_not_overwrite_existing_state(self):
        r = self._reg()
        r.define("temp", states={"cold":2})
        r.define("temp", states={"cold":99})  # 试图覆盖
        assert r.get("temp").states["cold"] == 2   # 原值保留

    # ── get ───────────────────────────────────────────────────
    def test_get_existing(self):
        r = self._reg()
        r.define("foo", states={"a":2})
        s = r.get("foo")
        assert s.name == "foo"

    def test_get_missing_raises(self):
        r = self._reg()
        with pytest.raises(KeyError, match="foo"):
            r.get("foo")

    def test_list_schemas(self):
        r = self._reg()
        r.define("s1", states={"a":2})
        r.define("s2", states={"b":3})
        assert set(r.list_schemas()) == {"s1", "s2"}

    # ── record_state ──────────────────────────────────────────
    def test_record_creates_store(self):
        r = self._reg()
        r.define("load", states={"high":5})
        r.record_state("load", subject="srv1", states=["high"], project="p1")
        store = r._get_store("p1", "load")
        assert len(store.events) == 1

    def test_record_log_value_correct(self):
        r = self._reg()
        r.define("load", states={"high":5})
        r.record_state("load", subject="srv1", states=["high"], project="p1")
        store = r._get_store("p1", "load")
        _, _, _, lv = store.events[0]
        assert lv == pytest.approx(math.log(5))

    def test_record_none_state_zero(self):
        r = self._reg()
        r.define("load", states={"low":2})
        r.record_state("load", subject="s", states=["none"], project="p1")
        store = r._get_store("p1", "load")
        _, _, _, lv = store.events[0]
        assert lv == 0.0

    def test_record_subject_indexed(self):
        r = self._reg()
        r.define("load", states={"ok":2})
        r.record_state("load", subject="alpha", states=["ok"], project="p")
        r.record_state("load", subject="beta",  states=["ok"], project="p")
        store = r._get_store("p", "load")
        subject_indices = {store.events[0][2], store.events[1][2]}
        assert subject_indices == {0, 1}

    def test_record_observer_default(self):
        r = self._reg()
        r.define("kv", states={"x":2})
        r.record_state("kv", subject="s", states=["x"],
                        observer="", project="p")
        store = r._get_store("p", "kv")
        obs_i = store.events[0][1]
        obs_name = list(store.observers.keys())[obs_i]
        assert obs_name == "__root__"

    def test_record_increments_counter(self):
        r = self._reg()
        r.define("m", states={"a":2})
        for _ in range(5):
            r.record_state("m", subject="s", states=["a"], project="p")
        store = r._get_store("p", "m")
        assert store.event_counter == 5

    def test_record_timestamps_count(self):
        r = self._reg()
        r.define("m", states={"a":2})
        for _ in range(3):
            r.record_state("m", subject="s", states=["a"], project="p")
        store = r._get_store("p", "m")
        assert len(store.timestamps) == 3

    def test_record_unknown_schema_raises(self):
        r = self._reg()
        with pytest.raises(KeyError):
            r.record_state("nonexistent", subject="s", states=["x"], project="p")

    # ── export ────────────────────────────────────────────────
    def test_export_creates_file(self, tmp_path):
        r = self._reg()
        r.define("load", states={"high":5})
        r.record_state("load", subject="s", states=["high"],
                        project="p", export_dir=str(tmp_path))
        path = r.export_schema("load", project="p",
                               filepath=str(tmp_path/"out.json"))
        assert Path(path).exists()

    def test_export_no_events_returns_none(self, tmp_path):
        r = self._reg()
        r.define("empty", states={"x":2})
        # 没有调用 record_state
        path = r.export_schema("empty", project="p")
        assert path is None

    def test_export_json_structure(self, tmp_path):
        r = self._reg()
        r.define("load", states={"high":5, "low":2},
                 dimensions=["server_id"], description="CPU")
        r.record_state("load", subject="srv1", states=["high"],
                        observer="agent", project="p", export_dir=str(tmp_path))
        path = r.export_schema("load", project="p",
                               filepath=str(tmp_path/"load.json"))
        d = json.loads(Path(path).read_text())
        assert d["metadata"]["schema"]      == "load"
        assert d["metadata"]["dimensions"]  == ["server_id"]
        assert d["metadata"]["description"] == "CPU"
        assert d["prime_map"]["high"]       == 5
        assert "subjects"  in d
        assert "observers" in d
        assert d["events_schema"] == ["t","observer_index","subject_index","log_value"]

    def test_export_subjects_list(self, tmp_path):
        r = self._reg()
        r.define("load", states={"ok":2})
        r.record_state("load", subject="s1", states=["ok"], project="p",
                        export_dir=str(tmp_path))
        r.record_state("load", subject="s2", states=["ok"], project="p",
                        export_dir=str(tmp_path))
        path = r.export_schema("load", project="p",
                               filepath=str(tmp_path/"o.json"))
        d = json.loads(Path(path).read_text())
        assert set(d["subjects"]) == {"s1", "s2"}

    def test_export_timestamps_relative(self, tmp_path):
        import time
        r = self._reg()
        r.define("load", states={"ok":2})
        r.record_state("load", subject="s", states=["ok"], project="p",
                        export_dir=str(tmp_path))
        time.sleep(0.01)
        r.record_state("load", subject="s", states=["ok"], project="p",
                        export_dir=str(tmp_path))
        path = r.export_schema("load", project="p",
                               filepath=str(tmp_path/"o.json"))
        d    = json.loads(Path(path).read_text())
        assert d["timestamps"][0] == pytest.approx(0.0)
        assert d["timestamps"][1] > 0

    def test_export_all_schemas(self, tmp_path):
        r = self._reg()
        r.define("s1", states={"a":2})
        r.define("s2", states={"b":3})
        r.record_state("s1", subject="x", states=["a"], project="p",
                        export_dir=str(tmp_path))
        r.record_state("s2", subject="y", states=["b"], project="p",
                        export_dir=str(tmp_path))
        paths = r.export_all_schemas(project="p", output_dir=str(tmp_path))
        assert len(paths) == 2

    # ── 线程安全 ──────────────────────────────────────────────
    def test_concurrent_record(self):
        r = self._reg()
        r.define("cnt", states={"tick":2})
        errors = []

        def worker():
            try:
                for _ in range(100):
                    r.record_state("cnt", subject="s", states=["tick"],
                                   project="p")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors
        store = r._get_store("p", "cnt")
        assert store.event_counter == 500

    # ── schema 文件 ───────────────────────────────────────────
    def test_save_and_load_schema_file(self, tmp_path):
        r = self._reg()
        r.define("biz", states={"ok":2,"warn":3,"err":5},
                 dimensions=["order_id"], description="Business KPI")
        r.save_schema_file("biz", str(tmp_path/"biz.json"))

        r2 = SchemaRegistry()
        r2.load_schema_file(str(tmp_path/"biz.json"))
        s = r2.get("biz")
        assert s.states["warn"]    == 3
        assert s.dimensions        == ["order_id"]
        assert s.description       == "Business KPI"


# ═══════════════════════════════════════════════════════════════
#  公开 API（通过 primelog 模块）
# ═══════════════════════════════════════════════════════════════
class TestPublicAPI:
    """验证 primelog.define_schema / record_state / export_schema 可用。"""

    def setup_method(self):
        """每个测试前用新 registry，避免全局状态泄漏。"""
        from primelog.core import schema_registry as _sr_mod
        self._old_sr = _sr_mod._schema_registry
        _sr_mod._schema_registry = SchemaRegistry()
        # 同步 primelog.__init__ 引用
        import primelog as pl
        pl._sr = _sr_mod._schema_registry

    def teardown_method(self):
        from primelog.core import schema_registry as _sr_mod
        _sr_mod._schema_registry = self._old_sr
        import primelog as pl
        pl._sr = self._old_sr

    def test_define_schema_returns_schema(self):
        s = primelog.define_schema("svc_health",
                                   states={"up":2,"degraded":3,"down":5},
                                   description="Service health")
        assert isinstance(s, Schema)
        assert s.name == "svc_health"

    def test_list_schemas(self):
        primelog.define_schema("aa", states={"x":2})
        primelog.define_schema("bb", states={"y":3})
        names = primelog.list_schemas()
        assert "aa" in names and "bb" in names

    def test_record_state_does_not_raise(self):
        primelog.define_schema("network", states={"ok":2,"loss":3})
        primelog.record_state(
            schema   = "network",
            subject  = "edge-router-01",
            states   = ["loss"],
            observer = "noc-agent",
        )

    def test_record_state_unknown_schema_raises(self):
        with pytest.raises(KeyError):
            primelog.record_state("ghost_schema", subject="x", states=["a"])

    def test_record_auto_alloc_prime(self):
        """没有手动指定素数时，record_state 自动分配。"""
        primelog.define_schema("auto", states={})  # 空 states
        primelog.record_state("auto", subject="s", states=["foo"])
        s = primelog._sr.get("auto")
        assert _is_prime(s.states["foo"])

    def test_export_schema_produces_file(self, tmp_path):
        primelog.define_schema("lat", states={"fast":2,"slow":5})
        primelog._sr.record_state(
            schema_name = "lat",
            subject     = "api",
            states      = ["slow"],
            project     = "__global__",
            export_dir  = str(tmp_path),
        )
        path = primelog._sr.export_schema(
            "lat", project="__global__",
            filepath=str(tmp_path/"lat.json")
        )
        assert path and Path(path).exists()
        d = json.loads(Path(path).read_text())
        assert d["metadata"]["schema"] == "lat"

    def test_full_workflow(self, tmp_path):
        """完整走一遍：定义 → 记录 → 导出 → 验证解码。"""
        primelog.define_schema(
            name        = "server_load",
            dimensions  = ["server_id", "time"],
            states      = {"low":2, "medium":3, "high":5, "critical":7},
            description = "Server CPU load level",
        )
        primelog._sr.record_state(
            schema_name = "server_load",
            subject     = "web-01",
            states      = ["high"],
            observer    = "monitor",
            project     = "__global__",
            export_dir  = str(tmp_path),
        )
        primelog._sr.record_state(
            schema_name = "server_load",
            subject     = "db-01",
            states      = ["critical"],
            observer    = "monitor",
            project     = "__global__",
            export_dir  = str(tmp_path),
        )
        path = primelog._sr.export_schema(
            "server_load", project="__global__",
            filepath=str(tmp_path/"server_load.json")
        )
        d = json.loads(Path(path).read_text())
        assert d["metadata"]["n_events"]    == 2
        assert "web-01" in d["subjects"]
        assert "db-01"  in d["subjects"]
        assert d["prime_map"]["high"]       == 5
        # 验证第一个事件能解码回 ["high"]
        schema = primelog._sr.get("server_load")
        lv = d["events"][0][3]
        assert schema.decode(lv) == ["high"]
