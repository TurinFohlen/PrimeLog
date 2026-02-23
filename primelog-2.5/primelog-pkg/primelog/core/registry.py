from dataclasses import dataclass, field, asdict
from typing import Dict, List, Callable, Any, Tuple, Optional
import inspect
import yaml
import os
import re
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager

# 导入默认关系类型-素数映射（需先创建 constants.py）
from .constants import RELATION_PRIME_MAP as DEFAULT_RELATION_MAP


@dataclass
class ComponentSpec:
    name: str
    type: str
    signature: str
    dependencies: List[str] = field(default_factory=list)
    typed_dependencies: List[Tuple[str, str]] = field(default_factory=list)  # (callee, relation_type)
    registration_order: int = 0
    source_file: str = ""
    class_name: str = ""


class Registry:
    def __init__(self, config_path: str = "components.yaml"):
        self.config_path = config_path
        self.components: Dict[str, ComponentSpec] = {}
        self.registration_counter = 0
        self.component_instances: Dict[str, Any] = {}
        self._load_existing()
        self._service_cache: Dict[str, Any] = {}
        # 运行时依赖追踪系统
        self.runtime_dependencies: Dict[str, set] = defaultdict(set)
        self._component_stack: List[str] = []
        self._track_depth = 0
        self._max_track_depth = 20

        # 关系类型到素数的映射（用于静态依赖矩阵）
        self.relation_prime_map = DEFAULT_RELATION_MAP.copy()
        self._load_relation_map_from_env()

    def _load_existing(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'components' in data:
                        for comp_data in data['components']:
                            spec = ComponentSpec(**comp_data)
                            # 兼容旧版本：如果没有 typed_dependencies，初始化为空
                            if not hasattr(spec, 'typed_dependencies'):
                                spec.typed_dependencies = []
                            self.components[spec.name] = spec
                            if spec.registration_order >= self.registration_counter:
                                self.registration_counter = spec.registration_order + 1
            except Exception as e:
                pass

    def _load_relation_map_from_env(self):
        """从环境变量 PRIMELOG_RELATION_MAP 加载关系类型映射
        格式示例：sync=2,async=3,rpc=5
        """
        env_map = os.environ.get("PRIMELOG_RELATION_MAP")
        if env_map:
            pairs = env_map.split(',')
            for pair in pairs:
                if '=' not in pair:
                    continue
                key, value = pair.split('=', 1)
                key = key.strip()
                try:
                    prime = int(value.strip())
                    self.relation_prime_map[key] = prime
                except ValueError:
                    pass  # 忽略无效值

    # ── 关系类型推断规则表（按优先级从高到低） ────────────────────
    # 每条规则：(匹配方法名的正则, 关系类型)
    # 注意：规则顺序即优先级，较具体的规则放前面
    _RELATION_RULES: List[Tuple["re.Pattern[str]", str]] = [
    # ============================================================
    # 超高频操作（应优先匹配，防止被后续通用规则误判）
    # ============================================================
    # I/O 操作（read/write/open/close 等）
    (re.compile(r'^(?:read_|write_|open_|close_|flush_|seek_|tell_|'
                r'load_(?:file|data|config)|save_(?:file|data|config)|'
                r'copy_|move_|rename_|delete_|remove_)'), 'io'),
    # 动态导入
    (re.compile(r'^(?:import_|load_module_|require_|__import__$)'), 'import'),
    (re.compile(r'^reload_module$'), 'import'),
    # 序列化
    (re.compile(r'^(?:serialize_|deserialize_|marshal_|unmarshal_|pickle_|unpickle_|'
                r'to_(?:json|yaml|xml|dict|bytes|str)|'
                r'from_(?:json|yaml|xml|dict|bytes|str))'), 'serialize'),
    # 日志
    (re.compile(r'^(?:debug_|info_|warn_|warning_|error_|critical_|log_|'
                r'log_(?:debug|info|warn|error|critical))'), 'log'),
    # 迭代
    (re.compile(r'^(?:iterate_|for_each_|each_|map_|filter_|reduce_|loop_|next_item$)'), 'iterate'),

    # ============================================================
    # 缓存操作（细分读写，比原 cache 更具体）
    # ============================================================
    # 缓存读取
    (re.compile(r'^(?:get_|read_|load_|retrieve_from_)cache$|cache_get$'), 'cache_get'),
    # 缓存写入
    (re.compile(r'^(?:set_|write_|save_|put_|store_)cache$|cache_set$'), 'cache_set'),
    # 原 cache 规则（作为后备，仍保留，但优先级降低）
    (re.compile(r'^(?:cache_|cached_|from_cache|'
                r'(?:get|set|del|invalidate)_cache|'
                r'cache(?:_get|_set|_del|_pop|_put)$)'), 'cache'),

    # ============================================================
    # 数据库查询（保持原样）
    # ============================================================
    (re.compile(r'^(?:query|fetch|select|find|search|lookup|'
                r'list_|count_|aggregate|join|filter|'
                r'get_(?:by|all|one|many|list|records?|rows?|entries|results?)|'
                r'insert|update|delete|upsert|bulk_)'), 'db_query'),

    # ============================================================
    # HTTP / 网络请求（保持原样，可适当扩充）
    # ============================================================
    (re.compile(r'^(?:post|put|patch|'
                r'http_|request_|call_api|send_request|'
                r'fetch_url|get_url|invoke_endpoint|'
                r'(?:get|post|put|delete)_(?:resource|endpoint|api))'), 'http_request'),

    # ============================================================
    # 文件 I/O（原有，与 io 部分重叠，但保留更细的 file_io）
    # ============================================================
    (re.compile(r'^(?:read_|write_|open_|load_file|save_|'
                r'store_|file_|parse_file|dump_|serialize|deserialize|'
                r'(?:read|write|load|save|parse)_(?:json|csv|yaml|xml|txt|config))'), 'file_io'),

    # ============================================================
    # 通知 / 消息（保持原样）
    # ============================================================
    (re.compile(r'^(?:send_(?:email|sms|push|notification|alert|message)|'
                r'notify|emit|publish|broadcast|alert_|push_|dispatch_event)'), 'notification'),

    # ============================================================
    # 校验（保持原样）
    # ============================================================
    (re.compile(r'^(?:validate|check_|verify_|assert_|is_valid|ensure_)'), 'validation'),

    # ============================================================
    # 锁操作（细分获取与通用）
    # ============================================================
    (re.compile(r'^(?:lock_acquire|acquire_lock|try_lock|obtain_lock)$'), 'lock_acquire'),
    (re.compile(r'^(?:lock|unlock|release_lock)$'), 'lock'),   # 通用锁操作

    # ============================================================
    # 事务（保持原样）
    # ============================================================
    (re.compile(r'^(?:begin_|commit|rollback|transaction|start_tx)'), 'transaction'),

    # ============================================================
    # 初始化（保持原样）
    # ============================================================
    (re.compile(r'^(?:init_|setup_|bootstrap_|create_|build_|start_)'), 'init'),

    # ============================================================
    # 销毁（保持原样）
    # ============================================================
    (re.compile(r'^(?:close_|destroy_|cleanup_|shutdown_|teardown_|stop_)'), 'destroy'),

    # ============================================================
    # 健康检查（保持原样）
    # ============================================================
    (re.compile(r'^(?:health|ping|status_check|is_alive|heartbeat)'), 'health_check'),

    # ============================================================
    # 指标采集（保持原样）
    # ============================================================
    (re.compile(r'^(?:metric_|measure_|record_metric|count_|gauge_|observe_)'), 'metrics'),

    # ============================================================
    # 配置读/写（保持原样）
    # ============================================================
    (re.compile(r'^(?:get_config|read_config|load_config)'), 'config_read'),
    (re.compile(r'^(?:set_config|write_config|save_config|update_config)'), 'config_write'),

    # ============================================================
    # 流水线（保持原样）
    # ============================================================
    (re.compile(r'^(?:pipe_|pipeline_|stream_|transform_|process_)'), 'pipeline'),

    # ============================================================
    # 内部调用通用后备（原样，优先级最低）
    # ============================================================
    (re.compile(r'^get_'), 'internal.sync'),
    (re.compile(r'^set_'), 'internal.sync'),
    (re.compile(r'^is_'), 'internal.sync'),
    (re.compile(r'^has_'), 'internal.sync'),
]

    @classmethod
    def _infer_relation_type(cls, source: str,
                             comp_name: str, comp_short: str,
                             class_name: str = "") -> str:
        """
        从源码中推断与 comp_name 的关系类型。

        策略（优先级递减）：
        1. 追踪赋值变量名（如 db = DBService() → db），再找 db.METHOD(
        2. 用 comp_short / comp_name 末段 / class_name 搜索 var.METHOD(
        3. 检测是否在 async def 块内调用 → internal.async
        4. 都没命中 → internal.sync（默认）
        """
        # ── 策略 1：追踪赋值变量名 ──────────────────────────────
        var_refs: set = set()
        var_refs.add(comp_short)

        # 所有可能代表该组件的标识符
        hints = {comp_short,
                 comp_short.replace('_', '').lower()}
        if class_name:
            hints.add(class_name)
            hints.add(class_name.lower())

        for line in source.splitlines():
            m = re.match(r'\s*(\w+)\s*=\s*.+', line)
            if m:
                var = m.group(1)
                rhs = line.split('=', 1)[1].lower()
                if any(h in rhs for h in hints):
                    var_refs.add(var)
            # get_service('comp.full.name') 赋值
            m2 = re.search(
                r'(\w+)\s*=.*get_service\(["\']' + re.escape(comp_name) + r'["\']',
                line
            )
            if m2:
                var_refs.add(m2.group(1))

        # ── 方法调用提取 ───────────────────────────────────────
        method_calls: List[str] = []
        for ref in var_refs:
            method_calls += re.findall(
                rf'\b{re.escape(ref)}\.(\w+)\s*\(', source
            )

        # 去重保序
        seen_m: set = set()
        unique = [m for m in method_calls if not (m in seen_m or seen_m.add(m))]

        for method in unique:
            for pattern, rel_type in cls._RELATION_RULES:
                if pattern.search(method):
                    return rel_type

        # ── 策略 2：async 上下文 ───────────────────────────────
        all_refs = {comp_name, comp_short} | (({class_name} if class_name else set()))
        for block in re.findall(
            r'async\s+def\s+\w+[^:]*:.*?(?=\nasync\s+def|\nclass\s|\Z)',
            source, re.DOTALL
        ):
            if any(ref in block for ref in all_refs):
                return 'internal.async'

        return 'internal.sync'

    def _analyze_dependencies(self, func_or_class) -> List[Tuple[str, str]]:
        """分析源码，返回 (被依赖组件名, 关系类型) 列表"""
        deps_with_types = []

        # 1. 通过 required_source 属性获取（类型由源码推断）
        if inspect.isclass(func_or_class) and hasattr(func_or_class, 'required_source'):
            req_source = func_or_class.required_source
            try:
                src_for_req = inspect.getsource(func_or_class)
            except Exception:
                src_for_req = ''
            candidates = ([req_source] if isinstance(req_source, str)
                          else list(req_source))
            for src_name in candidates:
                if src_name in self.components:
                    rel = self._infer_relation_type(
                        src_for_req, src_name, src_name.split('.')[-1]
                    )
                    deps_with_types.append((src_name, rel))

        # 2. 通过源码正则匹配，并推断具体关系类型
        try:
            source = inspect.getsource(func_or_class)
            for comp_name in self.components.keys():
                if comp_name == getattr(func_or_class, '__registry_name__', None):
                    continue
                if any(comp_name == dep for dep, _ in deps_with_types):
                    continue
                comp_short_name = comp_name.split('.')[-1]
                comp_class_name = self.components[comp_name].class_name or ''
                patterns = [
                    rf'\bsource\.{comp_short_name}\b',
                    rf'\bself\.source\.{comp_short_name}\b',
                    rf'["\']source\.{comp_name}["\']',
                    rf'\b{re.escape(comp_name)}\b',
                ]
                # 加上类名模式（普通 OOP 用法：DBService、CacheRepo 等）
                if comp_class_name:
                    patterns.append(rf'\b{re.escape(comp_class_name)}\b')
                for pattern in patterns:
                    if re.search(pattern, source):
                        rel_type = self._infer_relation_type(
                            source, comp_name, comp_short_name,
                            class_name=comp_class_name
                        )
                        deps_with_types.append((comp_name, rel_type))
                        break
        except Exception:
            pass

        # 去重
        seen = set()
        unique_deps = []
        for dep, typ in deps_with_types:
            if (dep, typ) not in seen:
                seen.add((dep, typ))
                unique_deps.append((dep, typ))
        return unique_deps

    def _build_adjacency_matrix(self) -> Dict[str, Any]:
        """构建静态依赖的带权 CSR 矩阵（仅使用 typed_dependencies）"""
        if not self.components:
            return {
                'nodes': [],
                'csr_format': {
                    'data': [],
                    'indices': [],
                    'row_ptrs': [0]
                },
                'relation_prime_map': self.relation_prime_map
            }

        sorted_components = sorted(
            self.components.values(),
            key=lambda x: x.registration_order
        )
        nodes = [c.name for c in sorted_components]
        node_to_idx = {name: idx for idx, name in enumerate(nodes)}

        data = []
        indices = []
        row_ptrs = [0]

        for comp in sorted_components:
            row_start = len(data)
            # 遍历 typed_dependencies
            for callee, rel_type in getattr(comp, 'typed_dependencies', []):
                if callee in node_to_idx:
                    prime = self.relation_prime_map.get(rel_type, 2)  # 默认素数2
                    data.append(prime)
                    indices.append(node_to_idx[callee])
            row_ptrs.append(len(data))

        return {
            'nodes': nodes,
            'csr_format': {
                'data': data,
                'indices': indices,
                'row_ptrs': row_ptrs
            },
            'relation_prime_map': self.relation_prime_map
        }

    def _flush(self):
        components_list = sorted(
            [asdict(c) for c in self.components.values()],
            key=lambda x: x['registration_order']
        )

        adjacency = self._build_adjacency_matrix()

        output = {
            'version': '1.0',
            'total_components': len(self.components),
            'components': components_list,
            'adjacency_matrix': adjacency
        }

        os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(
                output,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False
            )

    def register(self, name: str, type_: str, signature: str):
        def decorator(func_or_class):
            func_or_class.__registry_name__ = name

            try:
                source_file = inspect.getsourcefile(func_or_class) or ""
                source_file = os.path.relpath(source_file) if source_file else ""
            except:
                source_file = ""

            class_name = ""
            if inspect.isclass(func_or_class):
                class_name = func_or_class.__name__

            if name in self.components:
                spec = self.components[name]
                spec.type = type_
                spec.signature = signature
                spec.source_file = source_file
                spec.class_name = class_name
            else:
                spec = ComponentSpec(
                    name=name,
                    type=type_,
                    signature=signature,
                    registration_order=self.registration_counter,
                    source_file=source_file,
                    class_name=class_name
                )
                self.registration_counter += 1
                self.components[name] = spec

            # 使用新的依赖分析，同时填充 typed_dependencies 和 dependencies
            typed_deps = self._analyze_dependencies(func_or_class)
            spec.typed_dependencies = typed_deps
            spec.dependencies = [dep for dep, _ in typed_deps]  # 向后兼容

            self.component_instances[name] = func_or_class

            self._flush()

            return func_or_class
        return decorator

    def get_component(self, name: str) -> Optional[Any]:
        return self.component_instances.get(name)

    def get_spec(self, name: str) -> Optional[ComponentSpec]:
        return self.components.get(name)

    def get_service(self, name: str) -> Any:
        if name not in self.component_instances:
            raise KeyError(f"组件未注册: {name}")

        if name not in self._service_cache:
            cls = self.component_instances[name]
            self._service_cache[name] = cls()

        return self._service_cache[name]

    def list_components(self, type_filter: Optional[str] = None) -> List[ComponentSpec]:
        comps = list(self.components.values())
        if type_filter:
            comps = [c for c in comps if c.type == type_filter]
        return sorted(comps, key=lambda x: x.registration_order)

    def validate_dependencies(self) -> Tuple[bool, List[str]]:
        errors = []
        for spec in self.components.values():
            for dep in spec.dependencies:
                if dep not in self.components:
                    errors.append(f"Component '{spec.name}' depends on missing '{dep}'")
        return len(errors) == 0, errors

    def get_adjacency_matrix(self) -> Dict[str, Any]:
        return self._build_adjacency_matrix()

    # ================================================
    # 运行时依赖追踪核心方法
    # ================================================

    def _push_component(self, name: str):
        if name in self.component_instances:
            self._component_stack.append(name)

    def _pop_component(self):
        if self._component_stack:
            self._component_stack.pop()

    def _get_current_component(self) -> Optional[str]:
        return self._component_stack[-1] if self._component_stack else None

    def _record_runtime_dependency(self, callee: str):
        caller = self._get_current_component()
        if caller and caller != callee and callee in self.components:
            self.runtime_dependencies[caller].add(callee)

    @contextmanager
    def component_context(self, name: str):
        caller = self._get_current_component()
        self._push_component(name)
        try:
            yield
        except Exception as exc:
            try:
                from primelog.core.error_log import record_event, exception_to_error
                error_set = [exception_to_error(exc)]
                record_event(caller, name, error_set, self.components)
            except Exception:
                pass
            raise
        else:
            try:
                if caller is not None:
                    from primelog.core.error_log import record_event
                    record_event(caller, name, ["none"], self.components)
            except Exception:
                pass
        finally:
            self._pop_component()

    def _get_merged_deps(self, name: str) -> List[str]:
        if name not in self.components:
            return []
        static = set(self.components[name].dependencies)
        runtime = self.runtime_dependencies.get(name, set())
        return sorted(static | runtime)

    def _build_enhanced_adjacency(self) -> Dict[str, Any]:
        """构建包含运行时依赖的带权矩阵（运行时依赖使用默认素数）"""
        if not self.components:
            return {
                'nodes': [],
                'csr_format': {
                    'data': [],
                    'indices': [],
                    'row_ptrs': [0]
                },
                'relation_prime_map': self.relation_prime_map
            }

        sorted_components = sorted(
            self.components.values(),
            key=lambda x: x.registration_order
        )
        nodes = [c.name for c in sorted_components]
        node_to_idx = {name: idx for idx, name in enumerate(nodes)}

        # 构建静态依赖的素数映射：caller -> {callee: prime}
        static_prime_map = defaultdict(dict)
        for comp in sorted_components:
            for callee, rel_type in getattr(comp, 'typed_dependencies', []):
                if callee in node_to_idx:
                    static_prime_map[comp.name][callee] = self.relation_prime_map.get(rel_type, 2)

        data = []
        indices = []
        row_ptrs = [0]

        for comp in sorted_components:
            # 合并静态和运行时依赖
            merged = set(self._get_merged_deps(comp.name))
            for callee in merged:
                if callee not in node_to_idx:
                    continue
                # 优先使用静态素数，否则使用运行时默认素数
                if callee in static_prime_map[comp.name]:
                    prime = static_prime_map[comp.name][callee]
                else:
                    prime = self.relation_prime_map.get("runtime", 2)
                data.append(prime)
                indices.append(node_to_idx[callee])
            row_ptrs.append(len(data))

        return {
            'nodes': nodes,
            'csr_format': {
                'data': data,
                'indices': indices,
                'row_ptrs': row_ptrs
            },
            'relation_prime_map': self.relation_prime_map
        }

    # ================================================
    # 完全自动运行时上下文注入 + 源码扫描补盲
    # ================================================

    def _is_dunder(self, name: str) -> bool:
        return name.startswith('__') and name.endswith('__')

    def _wrap_callable(self, callable_obj, component_name: str):
        if not callable(callable_obj):
            return callable_obj
        import functools
        @functools.wraps(callable_obj)
        def wrapped(*args, **kwargs):
            with self.component_context(component_name):
                return callable_obj(*args, **kwargs)
        return wrapped

    def _auto_wrap_registered_component(self, name: str):
        if name not in self.component_instances:
            return
        obj = self.component_instances[name]
        if inspect.isclass(obj):
            for attr_name in dir(obj):
                if self._is_dunder(attr_name):
                    continue
                attr = getattr(obj, attr_name)
                if callable(attr):
                    wrapped = self._wrap_callable(attr, name)
                    setattr(obj, attr_name, wrapped)
        elif callable(obj):
            wrapped = self._wrap_callable(obj, name)
            self.component_instances[name] = wrapped

    def _scan_source_for_runtime_deps(self, name: str):
        if name not in self.components:
            return
        source_file = self.components[name].source_file
        if not source_file or not os.path.exists(source_file):
            return
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                source_code = f.read()

            lines = []
            for line in source_code.splitlines():
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    continue
                if '#' in line and not line.strip().startswith('"') and not line.strip().startswith("'"):
                    line = line.split('#', 1)[0].rstrip()
                lines.append(line)
            cleaned_code = '\n'.join(lines)

            cleaned_code = re.sub(r'""".*?"""', '', cleaned_code, flags=re.DOTALL)
            cleaned_code = re.sub(r"'''.*?'''", '', cleaned_code, flags=re.DOTALL)

            for other_name in list(self.components.keys()):
                if other_name == name:
                    continue
                if re.search(rf'\b{re.escape(other_name)}\b', cleaned_code):
                    self.runtime_dependencies[name].add(other_name)
        except:
            pass


# ================================================
# 无侵入方法包装（实现全自动运行时追踪）
# ================================================

_original_get_service = Registry.get_service
_original_build_adjacency_matrix = Registry._build_adjacency_matrix
_original_flush = Registry._flush
_original_register = Registry.register


def _tracked_get_service(self, name: str) -> Any:
    if self._track_depth >= self._max_track_depth:
        return _original_get_service(self, name)
    self._track_depth += 1
    try:
        self._record_runtime_dependency(name)
        return _original_get_service(self, name)
    finally:
        self._track_depth -= 1


def _tracked_build_adjacency_matrix(self) -> Dict[str, Any]:
    if self._track_depth >= self._max_track_depth:
        return _original_build_adjacency_matrix(self)
    self._track_depth += 1
    try:
        return self._build_enhanced_adjacency()
    finally:
        self._track_depth -= 1


def _tracked_flush(self):
    if self._track_depth >= self._max_track_depth:
        _original_flush(self)
        return
    self._track_depth += 1
    try:
        _original_flush(self)
    finally:
        self._track_depth -= 1


def _tracked_register(self, name: str, type_: str, signature: str):
    if self._track_depth >= self._max_track_depth:
        return _original_register(self, name, type_, signature)
    self._track_depth += 1
    try:
        original_decorator = _original_register(self, name, type_, signature)
        def enhanced_decorator(func_or_class):
            result = original_decorator(func_or_class)
            self._auto_wrap_registered_component(name)
            self._scan_source_for_runtime_deps(name)
            return result
        return enhanced_decorator
    finally:
        self._track_depth -= 1


# 应用所有 monkey-patch
Registry.get_service = _tracked_get_service
Registry._build_adjacency_matrix = _tracked_build_adjacency_matrix
Registry._flush = _tracked_flush
Registry.register = _tracked_register


import os as _os
_default_cfg = _os.path.join(_os.path.dirname(__file__), '..', 'components.yaml')
registry = Registry(config_path=_default_cfg)