# PrimeLog Wolfram 分析模板 v1.1

## 文件说明

| 文件 | 用途 |
|------|------|
| `primelog_template.wl` | 主模板：加载真实导出文件，完整分析流程 |
| `examples.wl` | 10 个独立可运行小例子（内嵌示例数据，无需导入文件） |

---

## 快速上手（Wolfram Cloud）

1. 打开 [Wolfram Cloud](https://www.wolframcloud.com) → New Notebook
2. 粘贴 `examples.wl` 全部内容
3. 按 `Shift+Enter` 逐格执行，或 `Evaluation → Evaluate Notebook`

不需要任何文件，数据已内嵌，直接出图。

---

## 配合真实 PrimeLog 数据使用（主模板）

```bash
# 先导出数据
primelog.export()
# 会生成：
#   adjacency_matrix_YYYYMMDD_HHMMSS.wl
#   error_events_compact_YYYYMMDD_HHMMSS.wl
```

把这两个文件和 `primelog_template.wl` 放在同一目录，打开模板执行即可。

---

## 10 个小例子说明

| 编号 | 功能 | 核心函数 |
|------|------|----------|
| Ex1 | 素数编码/解码验证 | `Log`, `Round[Exp[...]]` |
| Ex2 | 错误频率条形图 | `BarChart`, `Counts` |
| Ex3 | 组件对错误热力图 | `MatrixPlot`, `Total[errorTensor,{3}]` |
| Ex4 | 时间序列折线图 | `ListLinePlot`, 滑动窗口统计 |
| Ex5 | FFT 频谱分析 | `Fourier`, `Interpolation` |
| Ex6 | 静态依赖网络图 | `Graph`, `DirectedEdge` |
| Ex7 | 调用者/被调用者排行 | `BarChart`, 张量投影 |
| Ex8 | SVD 主要错误模式 | `SingularValueDecomposition` |
| Ex9 | 异常检测（3σ法） | `StandardDeviation`, 阈值标记 |
| Ex10 | 马尔可夫链传播概率 | `DiscreteMarkovProcess`（转移矩阵） |

---

## v1.0 → v1.1 修正

- `events[[5]]` 越界 → 改为 `events[[4]]`（紧凑版只有4字段）
- `AbsoluteTime[startTimestamp]` 改为 `AbsoluteTime[DateObject[startTimestamp]]`
- `errorTensor` 使用前确保已加载 `adjacency_matrix_*.wl`（提供 `n`）
- `decodeErrors` 返回空集时的容错处理
- 所有例子内嵌数据，无需外部依赖

---

## 数据格式参考（v3.0）

```wolfram
(* 事件格式：{t, caller_index, callee_index, log_value} *)
events[[1]]  (* → {1, 2, 3, 0.693147...} *)

(* 还原错误：*)
Round[Exp[events[[1, 4]]]]   (* → composite 整数 *)
decodeErrors[events[[1, 4]], primeMap]  (* → {"timeout"} *)

(* 时间戳：相对秒数，绝对起点见 startTimestamp *)
AbsoluteTime[DateObject[startTimestamp]] + timestamps[[1]]
```
