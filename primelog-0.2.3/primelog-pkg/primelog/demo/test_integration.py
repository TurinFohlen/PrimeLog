#!/usr/bin/env python3
"""集成测试：验证关系类型编码与导出"""

import primelog
import time
import os

# 设置日志根目录为项目根目录下的 logs
log_base = os.path.join(os.path.dirname(__file__), '..', 'logs')
primelog.init('test-project', log_base=log_base)

# 注册两个组件
@primelog.component('test-project.compA', type_='test', signature='call_b()')
class CompA:
    def call_b(self, should_fail=False):
        b = primelog.registry.get_service('test-project.compB')
        return b.do_something(should_fail)

@primelog.component('test-project.compB', type_='test', signature='do_something()')
class CompB:
    def do_something(self, should_fail=False):
        if should_fail:
            raise ValueError("模拟异常")
        return "ok"

# 正常调用
a = CompA()
result = a.call_b(should_fail=False)
print(f"正常调用结果: {result}")

# 异常调用
try:
    a.call_b(should_fail=True)
except ValueError:
    print("捕获到预期异常")

# 导出日志
primelog.export()
print("测试完成，请检查导出的日志文件。")