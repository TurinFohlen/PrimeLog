from dataclasses import dataclass, field, asdict
from typing import Dict, List, Callable, Any, Tuple, Optional
import inspect
import yaml
import os
import re
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager


@dataclass
class ComponentSpec:
    name: str
    type: str
    signature: str
    dependencies: List[str] = field(default_factory=list)
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
        # 【新增】运行时依赖追踪系统
        self.runtime_dependencies: Dict[str, set] = defaultdict(set)
        self._component_stack: List[str] = []
        self._track_depth = 0
        self._max_track_depth = 20  # 可配置，20层通常足够防栈溢出
    def _load_existing(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'components' in data:
                        for comp_data in data['components']:
                            spec = ComponentSpec(**comp_data)
                            self.components[spec.name] = spec
                            if spec.registration_order >= self.registration_counter:
                                self.registration_counter = spec.registration_order + 1
            except Exception as e:
                pass
    
    def _analyze_dependencies(self, func_or_class) -> List[str]:
        deps = []
        
        if inspect.isclass(func_or_class) and hasattr(func_or_class, 'required_source'):
            req_source = func_or_class.required_source
            if isinstance(req_source, str) and req_source in self.components:
                deps.append(req_source)
            elif isinstance(req_source, (list, tuple)):
                for src in req_source:
                    if src in self.components:
                        deps.append(src)
        
        try:
            source = inspect.getsource(func_or_class)
            
            for comp_name in self.components.keys():
                if comp_name == getattr(func_or_class, '__registry_name__', None):
                    continue
                if comp_name in deps:
                    continue
                
                comp_short_name = comp_name.split('.')[-1]
                
                patterns = [
                    rf'\bsource\.{comp_short_name}\b',
                    rf'\bself\.source\.{comp_short_name}\b',
                    rf'["\']source\.{comp_name}["\']',
                    rf'\b{comp_name}\b',
                ]
                
                for pattern in patterns:
                    if re.search(pattern, source):
                        if comp_name not in deps:
                            deps.append(comp_name)
                        break
        except Exception as e:
            pass
        
        return sorted(deps)
    
    def _build_adjacency_matrix(self) -> Dict[str, Any]:
        if not self.components:
            return {
                'nodes': [],
                'csr_format': {
                    'data': [],
                    'indices': [],
                    'row_ptrs': [0]
                }
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
            for dep in comp.dependencies:
                if dep in node_to_idx:
                    data.append(1)
                    indices.append(node_to_idx[dep])
            row_ptrs.append(len(data))
        
        return {
            'nodes': nodes,
            'csr_format': {
                'data': data,
                'indices': indices,
                'row_ptrs': row_ptrs
            }
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
            
            spec.dependencies = self._analyze_dependencies(func_or_class)
            
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
        """压栈当前执行组件"""
        if name in self.component_instances:
            self._component_stack.append(name)

    def _pop_component(self):
        """出栈"""
        if self._component_stack:
            self._component_stack.pop()

    def _get_current_component(self) -> Optional[str]:
        """获取当前执行组件"""
        return self._component_stack[-1] if self._component_stack else None

    def _record_runtime_dependency(self, callee: str):
        """自动记录运行时调用：当前组件 → callee"""
        caller = self._get_current_component()
        if caller and caller != callee and callee in self.components:
            self.runtime_dependencies[caller].add(callee)

    @contextmanager
    def component_context(self, name: str):
        """
        推荐上下文（支持嵌套）。
        【错误日志集成】在进入上下文前捕获 caller，退出时根据是否
        发生异常记录事件到 error_log 模块。
        """
        # 在压栈前获取当前调用者（栈顶即 caller）
        caller = self._get_current_component()
        self._push_component(name)
        try:
            yield
        except Exception as exc:
            # ── 异常路径：记录错误事件 ──
            try:
                from primelog.core.error_log import record_event, exception_to_error
                error_set = [exception_to_error(exc)]
                record_event(caller, name, error_set, self.components)
            except Exception:
                pass  # 日志失败不影响主流程
            raise  # 重新抛出，保持原有行为
        else:
            # ── 正常路径：记录无错误事件（仅当存在 caller 时）──
            try:
                if caller is not None:
                    from primelog.core.error_log import record_event
                    record_event(caller, name, ["none"], self.components)
            except Exception:
                pass
        finally:
            self._pop_component()

    def _get_merged_deps(self, name: str) -> List[str]:
        """合并静态 + 运行时依赖（不修改原有 spec）"""
        if name not in self.components:
            return []
        static = set(self.components[name].dependencies)
        runtime = self.runtime_dependencies.get(name, set())
        return sorted(static | runtime)

    def _build_enhanced_adjacency(self) -> Dict[str, Any]:
        """内部增强版构建（调用原有方法后叠加运行时边）"""
        base = _original_build_adjacency_matrix(self)
        if not self.components:
            return base

        sorted_components = sorted(self.components.values(), key=lambda x: x.registration_order)
        nodes = [c.name for c in sorted_components]
        node_to_idx = {n: i for i, n in enumerate(nodes)}

        data = []
        indices = []
        row_ptrs = [0]

        for comp in sorted_components:
            row_start = len(data)
            # 原有静态依赖保持不变
            for dep in comp.dependencies:
                if dep in node_to_idx:
                    data.append(1)
                    indices.append(node_to_idx[dep])
            # 叠加运行时依赖边（仅新增边，不重复）
            for dep in self._get_merged_deps(comp.name):
                if dep not in comp.dependencies and dep in node_to_idx:
                    data.append(1)
                    indices.append(node_to_idx[dep])
            row_ptrs.append(len(data))

        return {
            'nodes': nodes,
            'csr_format': {
                'data': data,
                'indices': indices,
                'row_ptrs': row_ptrs
            }
        }

    # ================================================
    # 完全自动运行时上下文注入 + 源码扫描补盲
    # ================================================

    def _is_dunder(self, name: str) -> bool:
        """判断是否双下划线方法"""
        return name.startswith('__') and name.endswith('__')

    def _wrap_callable(self, callable_obj, component_name: str):
        """包装任意可调用对象，自动进入组件上下文栈，保留原始签名"""
        if not callable(callable_obj):
            return callable_obj
        import functools
        @functools.wraps(callable_obj)
        def wrapped(*args, **kwargs):
            with self.component_context(component_name):
                return callable_obj(*args, **kwargs)
        return wrapped

    def _auto_wrap_registered_component(self, name: str):
        """自动包装已注册组件的所有 public 可调用成员（class 或 function）"""
        if name not in self.component_instances:
            return
        obj = self.component_instances[name]
        if inspect.isclass(obj):
            # 包装类中所有非dunder可调用方法
            for attr_name in dir(obj):
                if self._is_dunder(attr_name):
                    continue
                attr = getattr(obj, attr_name)
                if callable(attr):
                    wrapped = self._wrap_callable(attr, name)
                    setattr(obj, attr_name, wrapped)
        elif callable(obj):
            # 包装顶层函数
            wrapped = self._wrap_callable(obj, name)
            self.component_instances[name] = wrapped

    def _scan_source_for_runtime_deps(self, name: str):
        """依赖分析阶段源码扫描补盲：仅扫描自身 source_file，匹配其他已注册组件名"""
        if name not in self.components:
            return
        source_file = self.components[name].source_file
        if not source_file or not os.path.exists(source_file):
            return
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # 【新增】简单去掉 Python 单行注释（# 开头到行尾）和多行字符串注释
            # 保留代码准确性，减少误匹配
            lines = []
            for line in source_code.splitlines():
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    continue  # 跳过整行注释
                # 移除行内注释（# 后面部分），但保留字符串中的 #
                if '#' in line and not line.strip().startswith('"') and not line.strip().startswith("'"):
                    line = line.split('#', 1)[0].rstrip()
                lines.append(line)
            cleaned_code = '\n'.join(lines)

            # 【新增可选】进一步移除常见多行字符串（docstring）中的内容
            # 这里用简单正则移除 """...""" 和 '''...'''（非贪婪）
            cleaned_code = re.sub(r'""".*?"""', '', cleaned_code, flags=re.DOTALL)
            cleaned_code = re.sub(r"'''.*?'''", '', cleaned_code, flags=re.DOTALL)

            for other_name in list(self.components.keys()):
                if other_name == name:
                    continue
                # 使用原有匹配逻辑，但现在用清洗后的代码
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
        return _original_get_service(self, name)  # 超过深度，只执行不追踪
    self._track_depth += 1
    try:
        self._record_runtime_dependency(name)
        return _original_get_service(self, name)
    finally:
        self._track_depth -= 1


def _tracked_build_adjacency_matrix(self) -> Dict[str, Any]:
    if self._track_depth >= self._max_track_depth:
        return _original_build_adjacency_matrix(self)  # 原始版本（非 patch）
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