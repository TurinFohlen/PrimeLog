# primelog/core/error_constants.py
"""PrimeLog 错误类型素数映射表（独立文件）

此文件定义了内置错误类型与素数的对应关系。
如需添加新的错误类型，可在此处静态添加，或使用 register_error_type 动态注册。
素数必须唯一且大于1，'none' 固定为1（乘法单位元）。
"""

prime_map = {
    # 基础错误类型（无错误占位符）
    "none":             1,

    # 常用异常类映射（按字母顺序排列，便于查找）
    "assertion_error":  23,
    "attribute_error":  29,
    "connection_error": 31,      # 覆盖 ConnectionError 及其子类
    "disk_full":        11,
    "execution_error":  19,      # 通用执行错误
    "file_not_found":   5,
    "import_error":     37,
    "index_error":      41,
    "key_error":        43,
    "memory_error":     47,
    "network_error":    7,       # 涵盖超时、拒绝、重置等（若需细分可单独添加）
    "os_error":         53,      # 操作系统级错误（如设备不存在、权限等）
    "permission_denied":3,
    "recursion_error":  59,
    "runtime_error":    61,      # 其他运行时错误
    "stop_iteration":   67,      # 迭代结束（有时视为控制流，不是错误）
    "timeout":          2,
    "type_error":       71,
    "unknown":          17,
    "value_error":      73,
    "zero_division":    79,
}

# 预留给动态注册的素数候选列表
# 注意：此处仅作后备，若实际需要的错误类型超出列表，建议动态生成（如使用 sympy）
_next_prime_candidates = [83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157]