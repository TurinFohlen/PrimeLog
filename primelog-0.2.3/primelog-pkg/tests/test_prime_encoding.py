"""
test_prime_encoding.py
======================
测试 PrimeLog 的数学核心：
- composite_value()  素数乘积编码
- decode_errors()    唯一分解还原
- log_composite_value() 对数变换
- register_error_type() 动态素数分配
- exception_to_error()  异常类型映射

原则：每个测试只断言一件事，命名即文档。
"""

import unittest
import math
import importlib


def fresh_error_log():
    """每次返回干净模块（隔离 prime_map 全局状态）"""
    import primelog.core.error_log as el
    # 重置到默认 prime_map（避免测试间污染）
    el.prime_map.clear()
    el.prime_map.update({
        "none":              1,
        "timeout":           2,
        "permission_denied": 3,
        "file_not_found":    5,
        "network_error":     7,
        "disk_full":         11,
        "auth_failed":       13,
        "unknown":           17,
        "execution_error":   19,
    })
    el._next_prime_candidates[:] = [23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83]
    return el


class TestCompositeValue(unittest.TestCase):
    """composite_value()：素数乘积编码"""

    def setUp(self):
        self.el = fresh_error_log()

    def test_none_returns_1(self):
        """无错误 → 乘法单位元 1"""
        self.assertEqual(self.el.composite_value(["none"]), 1)

    def test_single_error_returns_its_prime(self):
        """单个错误 → 对应素数"""
        self.assertEqual(self.el.composite_value(["timeout"]), 2)
        self.assertEqual(self.el.composite_value(["permission_denied"]), 3)
        self.assertEqual(self.el.composite_value(["file_not_found"]), 5)

    def test_two_errors_returns_product(self):
        """两个错误 → 两素数之积"""
        # timeout(2) × file_not_found(5) = 10
        self.assertEqual(self.el.composite_value(["timeout", "file_not_found"]), 10)

    def test_three_errors_returns_product(self):
        """三个错误 → 三素数之积"""
        # timeout(2) × permission_denied(3) × file_not_found(5) = 30
        self.assertEqual(self.el.composite_value(["timeout", "permission_denied", "file_not_found"]), 30)

    def test_order_independent(self):
        """复合值与错误顺序无关（乘法交换律）"""
        v1 = self.el.composite_value(["timeout", "network_error"])
        v2 = self.el.composite_value(["network_error", "timeout"])
        self.assertEqual(v1, v2)

    def test_empty_list_returns_1(self):
        """空列表 → 1（reduce 的初始值）"""
        self.assertEqual(self.el.composite_value([]), 1)

    def test_unknown_key_maps_to_unknown_prime(self):
        """未知错误键 → 映射到 unknown(17)"""
        self.assertEqual(self.el.composite_value(["this_does_not_exist"]), 17)


class TestDecodeErrors(unittest.TestCase):
    """decode_errors()：唯一分解还原（算术基本定理）"""

    def setUp(self):
        self.el = fresh_error_log()

    def test_1_returns_none(self):
        """复合值=1 → ['none']"""
        self.assertEqual(self.el.decode_errors(1), ["none"])

    def test_0_returns_none(self):
        """复合值≤1 → ['none']"""
        self.assertEqual(self.el.decode_errors(0), ["none"])

    def test_single_prime_decodes_correctly(self):
        """单素数 → 对应单个错误"""
        self.assertIn("timeout", self.el.decode_errors(2))
        self.assertIn("permission_denied", self.el.decode_errors(3))
        self.assertIn("file_not_found", self.el.decode_errors(5))

    def test_product_decodes_to_both_errors(self):
        """乘积 → 两个错误都能还原"""
        # 2 × 5 = 10
        result = self.el.decode_errors(10)
        self.assertIn("timeout", result)
        self.assertIn("file_not_found", result)
        self.assertEqual(len(result), 2)

    def test_three_prime_product_decodes_all(self):
        """三素数乘积 → 三个错误全部还原"""
        composite = 2 * 3 * 5  # 30
        result = self.el.decode_errors(composite)
        self.assertIn("timeout", result)
        self.assertIn("permission_denied", result)
        self.assertIn("file_not_found", result)
        self.assertEqual(len(result), 3)

    def test_encode_decode_roundtrip(self):
        """编码后解码 = 原始错误集合（唯一性保证）"""
        original = ["timeout", "network_error"]
        composite = self.el.composite_value(original)
        restored = self.el.decode_errors(composite)
        self.assertEqual(set(restored), set(original))

    def test_roundtrip_single(self):
        errors = ["auth_failed"]
        self.assertEqual(set(self.el.decode_errors(self.el.composite_value(errors))), set(errors))

    def test_roundtrip_all_errors(self):
        """所有内置错误类型同时编码再解码"""
        errors = ["timeout", "permission_denied", "file_not_found",
                  "network_error", "disk_full", "auth_failed"]
        composite = self.el.composite_value(errors)
        restored = self.el.decode_errors(composite)
        self.assertEqual(set(restored), set(errors))


class TestLogCompositeValue(unittest.TestCase):
    """log_composite_value()：对数变换"""

    def setUp(self):
        self.el = fresh_error_log()

    def test_none_returns_zero(self):
        """无错误 → log(1) = 0.0"""
        self.assertAlmostEqual(self.el.log_composite_value(["none"]), 0.0)

    def test_single_error_returns_log_of_prime(self):
        """timeout(2) → log(2)"""
        self.assertAlmostEqual(
            self.el.log_composite_value(["timeout"]),
            math.log(2), places=10
        )

    def test_two_errors_log_equals_sum_of_logs(self):
        """log(p1 × p2) = log(p1) + log(p2)"""
        v = self.el.log_composite_value(["timeout", "file_not_found"])
        expected = math.log(2) + math.log(5)
        self.assertAlmostEqual(v, expected, places=10)

    def test_value_is_always_nonnegative(self):
        """对数值永远 ≥ 0"""
        for errors in [["none"], ["timeout"], ["timeout", "network_error"]]:
            self.assertGreaterEqual(self.el.log_composite_value(errors), 0.0)


class TestRegisterErrorType(unittest.TestCase):
    """register_error_type()：动态素数分配"""

    def setUp(self):
        self.el = fresh_error_log()

    def test_new_type_gets_assigned_prime(self):
        """新类型获得一个素数"""
        p = self.el.register_error_type("custom_error")
        self.assertGreater(p, 1)

    def test_same_name_returns_same_prime(self):
        """重复注册同一类型 → 返回同一素数"""
        p1 = self.el.register_error_type("my_error")
        p2 = self.el.register_error_type("my_error")
        self.assertEqual(p1, p2)

    def test_different_names_get_different_primes(self):
        """不同名称 → 不同素数"""
        p1 = self.el.register_error_type("error_alpha")
        p2 = self.el.register_error_type("error_beta")
        self.assertNotEqual(p1, p2)

    def test_registered_type_usable_in_composite(self):
        """动态注册的类型可以参与编码/解码"""
        p = self.el.register_error_type("db_timeout")
        composite = self.el.composite_value(["db_timeout"])
        self.assertEqual(composite, p)
        decoded = self.el.decode_errors(composite)
        self.assertIn("db_timeout", decoded)


class TestExceptionToError(unittest.TestCase):
    """exception_to_error()：异常类型映射"""

    def setUp(self):
        self.el = fresh_error_log()

    def test_timeout_error_maps_to_timeout(self):
        self.assertEqual(self.el.exception_to_error(TimeoutError()), "timeout")

    def test_permission_error_maps_to_permission_denied(self):
        self.assertEqual(self.el.exception_to_error(PermissionError()), "permission_denied")

    def test_file_not_found_maps_to_file_not_found(self):
        self.assertEqual(self.el.exception_to_error(FileNotFoundError()), "file_not_found")

    def test_connection_error_maps_to_network_error(self):
        self.assertEqual(self.el.exception_to_error(ConnectionError()), "network_error")

    def test_runtime_error_maps_to_execution_error(self):
        self.assertEqual(self.el.exception_to_error(RuntimeError()), "execution_error")

    def test_unknown_exception_maps_to_unknown(self):
        class WeirdError(Exception): pass
        self.assertEqual(self.el.exception_to_error(WeirdError()), "unknown")

    def test_result_is_valid_prime_map_key(self):
        """映射结果必须是 prime_map 中的合法键"""
        for exc in [TimeoutError(), PermissionError(), FileNotFoundError