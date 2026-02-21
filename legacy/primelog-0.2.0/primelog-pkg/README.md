# PrimeLog

**Decompose Anything. Understand Everything.**

基于**素数唯一分解定理**的通用组件日志与可观测性框架。任意组件调用事件被编码为单个整数，支持精确还原、统计分析、时间线可视化与 Wolfram Language 张量分析。

```
pip install primelog
```

---

## 核心思想

每种错误类型映射到唯一素数。一次调用的复合值 = 所有错误素数之积。

```
prime_map = { "none": 1, "timeout": 2, "file_not_found": 5, "permission_denied": 3, ... }

timeout + file_not_found  →  2 × 5 = 10
```

由唯一分解定理保证：`10` 只能还原为 `{timeout, file_not_found}`，信息无损。

---

## 五分钟上手

### 1. 安装

```bash
pip install primelog
# 含可视化分析工具
pip install primelog[analysis]
```

### 2. 给现有文件打印章

```bash
# 标记要扫描的目录
primelog loadmark -r ./my_project

# 给所有 service 文件打印章（自动插入 import 和装饰器）
primelog register ./my_project/*.py --type service --project my-project
```

### 3. 在入口脚本加三行

```python
import primelog

primelog.init('my-project')        # 设置项目名 + 日志目录
primelog.scan('./my_project')      # 扫描加载所有组件

# ... 你原来的代码，一行不用改 ...

primelog.export()                  # 导出日志 → ./logs/my-project/
```

### 4. 分析

```bash
primelog show-errors  --project my-project   # 错误事件详情
primelog stats        --project my-project   # 错误分布统计
primelog histogram    --project my-project   # ASCII 频率直方图
primelog timeline     --project my-project   # 时间线热力图/冲击波
primelog convert      --project my-project --format csv --output events.csv
```

---

## 架构

```
PrimeLogOrchestrator          ← 统一调度中心（单例）
    ├── core/registry.py      ← 注册器：组件发现 + 依赖追踪
    ├── core/loader.py        ← 加载器：自动扫描 __loadmark__ 目录
    ├── core/error_log.py     ← 报错器：素数编码事件记录
    ├── tools/                ← 分析工具层（读日志，不改系统）
    │   ├── histogram.py
    │   ├── timeline_visualization.py
    │   ├── timeline_analysis.py
    │   ├── exporter.py       ← CSV / JSONL / Elasticsearch
    │   ├── preprocess_events_for_fft.py
    │   ├── register_file.py  ← 自动打印章
    │   └── loadmark.py       ← 标记管理
    └── logs/log_librarian.py ← 日志归档（7z / tar）
```

三件套职责完全独立，工具层与核心完全解耦——系统扩展到 100+ 组件，工具一行不用改。

---

## Python API

```python
import primelog

# ── 初始化 ────────────────────────────────────────────────────
primelog.init('my-project')                 # 设置项目，日志 → ./logs/my-project/
primelog.init('my-project', log_base='/data/logs')  # 自定义日志根目录

# ── 注册组件（通常由 primelog register 命令自动插入）─────────
@primelog.component('my-project.algo.pso', type_='algorithm', signature='run() -> float')
class PSO:
    def run(self): ...

# ── 加载 ──────────────────────────────────────────────────────
primelog.scan('./my_project')               # 扫描所有 __loadmark__ 目录

# ── 运行（原代码不变）────────────────────────────────────────
result = PSO().run()

# ── 导出 ──────────────────────────────────────────────────────
primelog.export()                           # 用 init 设置的项目名
primelog.export(project='my-project')       # 显式指定
primelog.export(project='my-project', output_dir='/data/logs')

# ── 分析（Python 内直接调用，不需要 CLI）────────────────────
primelog.show_errors()                      # 错误事件详情
primelog.stats()                            # 错误分布
primelog.histogram(top=20, width=60, log_scale=True)
primelog.timeline(mode='heatmap', interval='5m')
primelog.timeline_analysis()                # 轻量按分钟统计
primelog.convert(fmt='csv', output='events.csv')
primelog.fft_prep(mode='count', bin_size=5.0)

# ── 运行时查询 ────────────────────────────────────────────────
stats = primelog.get_stats()
# {'total_events': 42, 'error_distribution': {'none': 40, 'timeout': 2}}
```

---

## CLI 命令大全

### 印章管理

```bash
# 标记目录（告诉 loader 去哪里扫描）
primelog loadmark ./my_project            # 只标记当前目录
primelog loadmark -r ./my_project         # 递归标记所有子目录
primelog loadmark -L 2 ./my_project       # 递归，限深度 2
primelog loadmark -x ./my_project         # 消除标记
primelog loadmark -xr ./my_project        # 递归消除

# 给文件打印章（自动插入 import + 装饰器）
primelog register myfile.py \
    --type service \
    --project my-project \
    --signature "run() -> None"

primelog register algorithms/*.py --type algorithm --project my-project
```

### 扫描加载

```bash
primelog scan ./my_project
```

### 日志分析

```bash
# 基础分析
primelog show-errors --project my-project
primelog stats       --project my-project

# 可视化
primelog histogram   --project my-project --top 20 --width 80 --log
primelog timeline    --project my-project --mode heatmap --interval 5m
primelog timeline    --project my-project --mode wave
primelog timeline    --project my-project --mode timeline --top 10
primelog timeline-analysis --project my-project

# 导出对接外部工具
primelog convert --project my-project --format csv     --output events.csv
primelog convert --project my-project --format jsonl   --output events.jsonl
primelog convert --project my-project --format elastic --output bulk.json

# 过滤导出
primelog convert --project my-project \
    --format csv \
    --error-types timeout,file_not_found \
    --start 2026-02-20T00:00:00 \
    --output filtered.csv

# FFT 分析预处理
primelog fft-prep --project my-project --mode count --bin-size 5.0
```

### 归档维护

```bash
primelog archive --project my-project --keep 30         # 保留最近30天
primelog archive --project my-project --compressor 7z   # 用 7z 压缩
primelog export  --project my-project --out /data/logs  # 手动导出
```

---

## 多项目隔离

不同项目使用同一个 PrimeLog 安装，通过**项目名命名空间**完全隔离。

```python
# 项目 A
import primelog
primelog.init('pocket-optimizer')
@primelog.component('pocket-optimizer.algo.pso', ...)   # 前缀不同，永不冲突

# 项目 B
import primelog
primelog.init('data-pipeline')
@primelog.component('data-pipeline.extractor', ...)
```

日志自动写入独立子目录：

```
logs/
├── pocket-optimizer/
│   ├── error_events_20260221.json
│   └── adjacency_matrix_20260221.json
└── data-pipeline/
    └── error_events_20260221.json
```

---

## 自观测

Orchestrator 本身注册为 `primelog.core.orchestrator` 组件，自身的调度行为同样被 error_log 追踪。PrimeLog 用自己的系统观测自己。

---

## Wolfram Language 集成

导出的 `.wl` 文件可直接在 Mathematica 中加载：

```mathematica
Get["error_events_20260221.wl"]
(* 获得 errorTensor，可直接做张量分解、聚类、FFT *)
MatrixPlot[errorTensor]
SingularValueDecomposition[errorTensor]
```

---

## 版本历史

| 版本 | 主要内容 |
|------|----------|
| v0.2.0 | Orchestrator 统一调度中心；全工具集成（histogram/timeline/convert/fft-prep）；自观测；多项目事件状态隔离 |
| v0.1.3 | loadmark 命令；register 自动打印章；多项目命名空间 |
| v0.1.0 | 核心三件套；CLI 基础命令；pip 可安装包 |

---

## License

MPL-2.0 · RoseHammer · [github.com/TurinFohlen/PrimeLog](https://github.com/TurinFohlen/PrimeLog)
