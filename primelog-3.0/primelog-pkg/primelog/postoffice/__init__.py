"""
primelog.postoffice — 信息素驱动的分布式日志汇聚模块

主要类：
    Postmare   主守护进程（组装三层）
    Bridge     PrimeLog 导出 → mailbag 投递桥接

快速上手：
    from primelog.postoffice.bridge import Bridge
    bridge = Bridge(mailbag_dir='./postoffice/Project1/mailbag')
    bridge.export_and_deliver(project='my-project')
"""

from .bridge import Bridge

__all__ = ['Bridge']
