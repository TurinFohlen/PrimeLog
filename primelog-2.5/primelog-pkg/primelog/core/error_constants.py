# primelog/core/error_constants.py
"""PrimeLog 错误类型素数映射表（独立文件）"""

prime_map = {
    "none":             1,
    "timeout":          2,
    "permission_denied":3,
    "file_not_found":   5,
    "network_error":    7,
    "disk_full":        11,
    "auth_failed":      13,
    "unknown":          17,
    "execution_error":  19,
    # HTTP 状态码相关错误（虚拟外部组件 / call_external 使用）
    "http_400":         23,   # Bad Request
    "http_401":         29,   # Unauthorized
    "http_403":         31,   # Forbidden
    "http_404":         37,   # Not Found
    "http_500":         41,   # Internal Server Error
    "http_502":         43,   # Bad Gateway
    "http_503":         47,   # Service Unavailable
    "http_504":         53,   # Gateway Timeout
}

_next_prime_candidates = [59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113]