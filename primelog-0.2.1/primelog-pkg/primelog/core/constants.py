# primelog/core/constants.py
"""PrimeLog 内部关系类型素数映射表"""

RELATION_PRIME_MAP = {
    # 基础内部调用类型
    "internal.sync": 2,      # 同步调用（默认）
    "internal.async": 3,     # 异步调用
    "internal.event": 5,     # 事件触发
    "internal.config": 7,    # 配置读取/写入
    "internal.registry": 11, # 注册中心操作
    "runtime": 13,           # 运行时依赖（非静态）

    # 具体交互模式（后端常见）
    "rpc": 17,               # 远程过程调用
    "db_query": 19,          # 数据库查询
    "file_io": 23,           # 文件读写
    "http_request": 29,      # HTTP 请求
    "pipeline": 31,          # 数据管道/流式处理
    "init": 37,              # 初始化过程
    "destroy": 41,           # 资源销毁
    "health_check": 43,      # 健康检查
    "metrics": 47,           # 指标收集
    "config_read": 53,       # 配置读取
    "config_write": 59,      # 配置写入
    "cache": 61,             # 缓存操作
    "lock": 67,              # 锁操作
    "transaction": 71,       # 事务操作
    "validation": 73,        # 数据验证
    "notification": 79,      # 通知发送
}