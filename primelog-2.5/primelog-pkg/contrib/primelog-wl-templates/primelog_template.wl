(* ::Package:: *)

(*
PrimeLog 通用分析模板 v1.1
==================================================
修正 v1.0 的以下问题：
  - events[[5]] 越界 → 改为 events[[4]]（紧凑版只有4字段）
  - AbsoluteTime[startTimestamp] 解析方式修正
  - errorTensor 依赖 n，需先加载邻接矩阵
  - decodeErrors 返回值在空集时的处理

使用方法：
  1. 将本文件与导出的 adjacency_matrix_*.wl 和
     error_events_compact_*.wl 放在同一目录。
  2. 在 Wolfram Cloud Notebook 中：New Notebook → 粘贴 → Shift+Enter 逐格执行。
  3. 本地 Mathematica：File → Open → 执行所有单元格（Evaluation → Evaluate Notebook）。

数据变量说明（加载后可用）：
  邻接矩阵文件：nodes, n, relationPrimeMap, staticDepA
  事件文件：    primeMap, startTimestamp, timestamps, events, totalT,
               errorTensor, decodeErrors（函数）
*)

(* ========== 0. 环境准备 ========== *)
SetDirectory[NotebookDirectory[]];

(* ========== 1. 自动加载最新数据文件 ========== *)
adjFiles = Sort[FileNames["adjacency_matrix_*.wl"]];
errFiles = Sort[FileNames["error_events_compact_*.wl"]];

(* 如果没有紧凑版，尝试可读版 *)
If[Length[errFiles] == 0,
   errFiles = Sort[FileNames["error_events_*.wl"]]];

If[Length[adjFiles] == 0 || Length[errFiles] == 0,
   Print["错误：目录中未找到 .wl 文件，请确认文件路径。"];
   Abort[]];

(* 取最新文件（按文件名排序，时间戳在文件名中） *)
latestAdj = Last[adjFiles];
latestErr = Last[errFiles];

Print["加载邻接矩阵：", latestAdj];
Get[latestAdj];   (* 定义：nodes, n, relationPrimeMap, staticDepA *)

Print["加载错误事件：", latestErr];
Get[latestErr];   (* 定义：primeMap, startTimestamp, timestamps, events,
                            totalT, errorTensor, decodeErrors *)

(* ========== 2. 数据校验 ========== *)
Print["\n✅ 数据加载成功"];
Print["  组件数量：", n];
Print["  事件总数：", totalT];

(* v3.0 时间戳为相对秒数，startTimestamp 为绝对起点字符串 *)
startAbs = AbsoluteTime[DateObject[startTimestamp]];
endAbs   = startAbs + Max[timestamps];
Print["  时间范围：", startTimestamp, "  +",
      NumberForm[Max[timestamps], {6,3}], " 秒"];
Print["  前5个组件：", Take[nodes, Min[5, n]]];
Print["  错误类型：", Keys[primeMap]];

(* ========== 3. 工具函数 ========== *)

(* 从 log_value 解码错误列表（紧凑版事件用） *)
(* decodeErrors 已由事件文件定义，这里提供一个带容错的包装 *)
safeDecodeErrors[logValue_] :=
  Module[{result},
    result = decodeErrors[logValue, primeMap];
    If[result === {} || result === Null, {"unknown"}, result]
  ];

(* 获取组件名（索引从1开始） *)
compName[idx_Integer] :=
  If[1 <= idx <= n, nodes[[idx]], "unknown#" <> ToString[idx]];

(* ========== 4. 错误统计 ========== *)
Print["\n=== 错误类型分布 ==="];
(* events[[i]] = {t, caller_idx, callee_idx, log_value} *)
allErrors = Flatten[safeDecodeErrors[#[[4]]] & /@ events];
errorCounts = Sort[Normal[Counts[allErrors]], #1[[2]] > #2[[2]] &];
Print[errorCounts // TableForm];

(* ========== 5. 组件错误热力图 ========== *)
Print["\n=== 组件对错误热力图 ==="];
(* 对 errorTensor 在时间维度求和，得到 n×n 的错误矩阵 *)
errMatrix = Total[Normal[errorTensor], {3}];
MatrixPlot[errMatrix,
  PlotLabel -> "组件间错误总量（对数值之和）",
  FrameLabel -> {"调用者（callee）", "被调用者（caller）"},
  ColorFunction -> "TemperatureMap",
  ColorFunctionScaling -> True]

(* ========== 6. 时间序列：总错误量随时间变化 ========== *)
Print["\n=== 时间序列 ==="];
(* 每个事件时刻的 log_value *)
logValues = events[[All, 4]];
ListLinePlot[Transpose[{timestamps, logValues}],
  PlotLabel -> "错误 log_value 随时间变化",
  AxesLabel -> {"时间偏移（秒）", "log_value"},
  Filling -> Axis,
  PlotStyle -> Directive[Blue, Opacity[0.7]]]

(* ========== 7. 依赖图可视化 ========== *)
Print["\n=== 静态依赖图 ==="];
depRules = Select[ArrayRules[staticDepA], #[[2]] =!= 0 &];
If[Length[depRules] > 0,
  Graph[
    (compName[#[[1,1]]] -> compName[#[[1,2]]]) & /@ depRules,
    EdgeLabels -> (Rule[compName[#[[1,1]]] -> compName[#[[1,2]]],
                        #[[2]]] & /@ depRules),
    VertexStyle -> Directive[LightBlue, EdgeForm[Gray]],
    GraphLayout -> "LayeredDigraphEmbedding",
    PlotLabel -> "静态依赖图（边权值为关系类型素数）"],
  Print["  （无静态依赖关系）"]
];

(* ========== 8. 自定义分析区域 ========== *)
Print["\n=== 8. 在此添加自定义分析 ==="];
(* 示例占位，取消注释即可运行：

  (* FFT 频谱分析 *)
  fftResult = Abs[Fourier[logValues]];
  ListLinePlot[fftResult[[1 ;; Floor[Length[fftResult]/2]]],
    PlotLabel -> "错误频谱（FFT）",
    AxesLabel -> {"频率分量", "幅度"}]

  (* 聚类 *)
  featureMatrix = events[[All, {2,3,4}]];  (* caller, callee, log_value *)
  clusters = FindClusters[featureMatrix, 3];
  Print["聚类结果（3类）：", Length /@ clusters, " 条事件"]

  (* 相关性 *)
  callerErrVec = Table[
    Total[Normal[errorTensor][[i, All, All]], 2], {i, n}];
  MatrixPlot[Correlation[Transpose[{callerErrVec}]],
    PlotLabel -> "调用者错误相关性矩阵"]
*)

(* ========== 9. 导出结果 ========== *)
Export["error_counts.csv",
  Prepend[errorCounts, {"错误类型", "出现次数"}]];
Print["错误统计已保存到 error_counts.csv"];

Print["\n✅ 模板执行完毕。"];
