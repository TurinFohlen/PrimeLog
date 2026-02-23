#!/usr/bin/env python3
"""
test_scarecrow.py — 外部 API 追踪（稻草人）功能测试
不需要真实网络：全部使用 mock
"""
import sys, os, math, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'primelog'))

import primelog
from primelog.core.error_log import exception_to_error, prime_map, decode_errors
from primelog.core.registry  import registry

PASS, FAIL = [], []
def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  [{detail}]" if not cond else ''))


# ══════════════════════════════════════════════════
# 1. HTTP 错误类型已注册到 prime_map
# ══════════════════════════════════════════════════
print('\n─── 1. prime_map 包含 HTTP 错误 ───')
http_errors = ["http_400","http_401","http_403","http_404",
               "http_500","http_502","http_503","http_504"]
for e in http_errors:
    check(f"prime_map[{e}] 存在", e in prime_map)

# 素数唯一性
all_vals = list(prime_map.values())
check("prime_map 无重复素数", len(all_vals) == len(set(all_vals)))

# log_value 可逆
for e in http_errors:
    p   = prime_map[e]
    lv  = math.log(p)
    dec = decode_errors(round(math.exp(lv)))
    check(f"{e} 编解码一致", dec == [e], f"got {dec}")


# ══════════════════════════════════════════════════
# 2. exception_to_error 识别异常消息字符串
# ══════════════════════════════════════════════════
print('\n─── 2. exception_to_error 异常消息匹配 ───')
check("http_404 消息识别", exception_to_error(Exception("http_404")) == "http_404")
check("http_500 消息识别", exception_to_error(Exception("http_500")) == "http_500")
check("timeout 消息识别",  exception_to_error(Exception("timeout"))  == "timeout")
check("network_error 消息识别", exception_to_error(Exception("network_error")) == "network_error")
check("未知消息→unknown",  exception_to_error(Exception("something weird")) == "unknown")
# 原有类型匹配不受影响
check("TimeoutError 类型匹配", exception_to_error(TimeoutError()) == "timeout")
check("ConnectionError 类型匹配", exception_to_error(ConnectionError()) == "network_error")


# ══════════════════════════════════════════════════
# 3. register(None)：虚拟组件注册
# ══════════════════════════════════════════════════
print('\n─── 3. 虚拟组件注册 ───')
result = registry.register(
    name="test-proj.mock-api",
    type_="external",
    signature="GET https://api.example.com/test"
)(None)
check("register(None) 返回 None",  result is None)
spec = registry.get_spec("test-proj.mock-api")
check("虚拟组件 spec 存在",        spec is not None)
check("type = external",           spec and spec.type == "external")
check("signature 正确",            spec and "mock-api" in spec.signature or "example.com" in (spec.signature if spec else ""))

# metadata 可以设置
if spec:
    spec.metadata = {"url": "https://api.example.com/test", "method": "GET", "timeout": 5}
check("metadata 可设置",           spec and spec.metadata.get("url") == "https://api.example.com/test")


# ══════════════════════════════════════════════════
# 4. register_external() 便捷接口
# ══════════════════════════════════════════════════
print('\n─── 4. register_external ───')
import primelog
with tempfile.TemporaryDirectory() as tmp:
    primelog.init('scarecrow-test', log_base=tmp)
    primelog.register_external(
        name="user-service",
        url="https://users.example.com/v1",
        method="GET",
        timeout=8,
        project="scarecrow-test",
    )
    spec2 = registry.get_spec("scarecrow-test.user-service")
    check("register_external spec 存在", spec2 is not None)
    check("type = external",             spec2 and spec2.type == "external")
    check("metadata.url 正确",          spec2 and spec2.metadata.get("url") == "https://users.example.com/v1")
    check("metadata.timeout 正确",      spec2 and spec2.metadata.get("timeout") == 8)


# ══════════════════════════════════════════════════
# 5. _register_external_components：从 externals.json 批量注册
# ══════════════════════════════════════════════════
print('\n─── 5. externals.json 批量注册 ───')
with tempfile.TemporaryDirectory() as tmp:
    import os
    cfg_dir = os.path.join(tmp, 'missionlist')
    os.makedirs(cfg_dir)
    ext_data = {
        "payment-svc": {
            "url": "https://pay.example.com/charge",
            "method": "POST",
            "timeout": 15,
        },
        "geo-api": {
            "url": "https://geo.example.com/lookup",
            "method": "GET",
            "timeout": 5,
            "auth": {"type": "bearer", "token": "env:GEO_TOKEN"},
        }
    }
    with open(os.path.join(cfg_dir, 'externals.json'), 'w') as f:
        json.dump(ext_data, f)

    primelog._register_external_components("batch-proj", config_dir=tmp)

    s1 = registry.get_spec("batch-proj.payment-svc")
    s2 = registry.get_spec("batch-proj.geo-api")
    check("payment-svc 已注册",     s1 is not None)
    check("geo-api 已注册",         s2 is not None)
    check("payment-svc method=POST", s1 and s1.metadata.get("method") == "POST")
    check("geo-api auth 保留",      s2 and s2.metadata.get("auth", {}).get("type") == "bearer")


# ══════════════════════════════════════════════════
# 6. call_external：mock 网络调用，验证事件记录
# ══════════════════════════════════════════════════
print('\n─── 6. call_external 事件记录 ───')

# 用 unittest.mock 模拟 requests
from unittest.mock import MagicMock, patch

class FakeResponse:
    def __init__(self, status):
        self.status_code = status
        self._json = {"ok": True}
    def json(self): return self._json

with tempfile.TemporaryDirectory() as tmp:
    primelog.init('api-test', log_base=tmp)
    primelog.register_external(
        name="search",
        url="https://search.example.com/q",
        project="api-test",
    )
    primelog.register_external(
        name="missing",
        url="https://search.example.com/missing",
        project="api-test",
    )

    # -- 6a: 成功调用（200）
    with patch("requests.request", return_value=FakeResponse(200)):
        resp = primelog.call_external("search", project="api-test", params={"q": "test"})
    check("200 成功返回 response", resp is not None and resp.status_code == 200)

    # -- 6b: 404 调用→事件里有 http_404
    from primelog.core.error_log import _project_store, _thread_local
    key = getattr(_thread_local, 'project_key', None)
    events_before = len(_project_store.get(key, {}).get('events', []))

    with patch("requests.request", return_value=FakeResponse(404)):
        try:
            primelog.call_external("missing", project="api-test")
        except Exception as e:
            exc_msg = str(e)

    events_after = _project_store.get(key, {}).get('events', [])
    check("404 抛出异常",           exc_msg == "http_404")
    check("404 产生新事件",         len(events_after) > events_before)
    if events_after:
        last_ev = events_after[-1]
        err_set = last_ev[3]  # (t, caller_idx, callee_idx, error_set)
        check("事件 error_set = [http_404]", err_set == ["http_404"], f"got {err_set}")

    # -- 6c: Timeout
    import requests as _req
    with patch("requests.request", side_effect=_req.exceptions.Timeout()):
        try:
            primelog.call_external("search", project="api-test")
        except Exception as e:
            timeout_msg = str(e)
    check("Timeout 映射为 timeout 错误", timeout_msg == "timeout")

    # -- 6d: ConnectionError
    with patch("requests.request", side_effect=_req.exceptions.ConnectionError()):
        try:
            primelog.call_external("search", project="api-test")
        except Exception as e:
            conn_msg = str(e)
    check("ConnectionError 映射为 network_error", conn_msg == "network_error")

    # -- 6e: 未注册的组件
    raised = False
    try:
        primelog.call_external("nonexistent", project="api-test")
    except ValueError:
        raised = True
    check("未注册组件抛 ValueError", raised)


# ══════════════════════════════════════════════════
# 7. 事件格式与内部组件完全一致
# ══════════════════════════════════════════════════
print('\n─── 7. 事件格式与内部组件一致 ───')
with tempfile.TemporaryDirectory() as tmp:
    primelog.init('format-test', log_base=tmp)

    # 内部组件
    @primelog.component('format-test.internal', type_='s', signature='')
    class Internal:
        def run(self):
            with registry.component_context('format-test.ext-svc'):
                raise Exception("http_503")

    # 虚拟外部组件
    primelog.register_external("ext-svc", "https://svc.example.com", project="format-test")

    try:
        with registry.component_context('format-test.internal'):
            Internal().run()
    except Exception:
        pass

    key2 = getattr(_thread_local, 'project_key', None)
    evs  = _project_store.get(key2, {}).get('events', [])
    check("有事件被记录", len(evs) > 0)
    if evs:
        # 每个事件：(t, caller_idx, callee_idx, error_set)
        last = evs[-1]
        check("事件有4个字段", len(last) == 4)
        check("error_set 是列表", isinstance(last[3], list))
        check("错误为 http_503", "http_503" in last[3], f"got {last[3]}")


# ══════════════════════════════════════════════════
print(f'\n{"─"*45}')
print(f'通过 {len(PASS)}/{len(PASS)+len(FAIL)}')
if FAIL:
    print(f'失败项: {FAIL}')
    sys.exit(1)
else:
    print('全部通过 ✅')
