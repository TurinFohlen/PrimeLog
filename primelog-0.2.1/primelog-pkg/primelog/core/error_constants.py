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
}

_next_prime_candidates = [23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83]