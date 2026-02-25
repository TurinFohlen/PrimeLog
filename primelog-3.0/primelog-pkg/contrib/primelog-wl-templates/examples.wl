(* ::Package:: *)

(*
PrimeLog 可运行小例子集 v1.0
==================================================
每个例子都是自包含的：内嵌了最小示例数据，
无需加载外部文件，直接粘贴到 Wolfram Cloud Notebook 即可运行。

目录：
  Ex1  - 素数编码与解码（数学核心验证）
  Ex2  - 错误频率条形图
  Ex3  - 组件对错误热力图
  Ex4  - 时间序列折线图
  Ex5  - FFT 频谱分析
  Ex6  - 静态依赖网络图
  Ex7  - 调用者/被调用者错误排行
  Ex8  - 奇异值分解（SVD）提取主要错误模式
  Ex9  - 简单异常检测（均值 ± 3σ）
  Ex10 - 马尔可夫链：错误传播概率
*)

(* ──────────────────────────────────────────────────
   内嵌示例数据（所有例子共用）
   模拟一个 4 组件微服务系统，100 个事件
   ────────────────────────────────────────────────── *)
primeMap = <|"none"->1, "timeout"->2, "permission_denied"->3,
             "file_not_found"->5, "network_error"->7, "auth_failed"->13,
             "unknown"->17, "execution_error"->19|>;

nodes = {"svc.api", "svc.auth", "svc.db", "svc.cache"};
n = 4;

(* 生成确定性模拟数据（seed固定，可复现） *)
SeedRandom[42];
nEvents = 100;

(* 随机错误组合的 log_value：70% none, 20% timeout, 7% network_error, 3% 多错误 *)
randomLogValue[] := RandomChoice[
  {0.70, 0.20, 0.07, 0.03} ->
  {Log[1], Log[2], Log[7], Log[2*7]}];

(* events = {t, caller(1-4), callee(1-4), log_value} *)
events = Table[
  {i,
   RandomInteger[{1,4}],
   RandomInteger[{1,4}],
   randomLogValue[]},
  {i, nEvents}];

(* 相对时间戳（秒），模拟平均每秒5个事件 *)
timestamps = Accumulate[RandomVariate[ExponentialDistribution[5], nEvents]];
startTimestamp = "2026-02-22T10:00:00";

(* 静态依赖矩阵（api→auth=runtime(101), auth→db=db_query(17), api→cache=cache(113)） *)
staticDepA = SparseArray[{{1,2}->101, {2,3}->17, {1,4}->113}, {n,n}];

(* 错误张量 errorTensor[[caller, callee, t]] *)
errorTensor = SparseArray[
  Table[{events[[i,2]], events[[i,3]], i} -> events[[i,4]], {i,nEvents}],
  {n, n, nEvents}];

(* 工具函数 *)
decodeErrors[lv_] := Module[{c = Round[Exp[lv]], res = {}},
  If[c <= 1, Return[{"none"}]];
  Do[If[Mod[c, p] == 0,
        AppendTo[res, name];
        While[Mod[c,p]==0, c=c/p]],
     {name, Keys[primeMap]}, {p, Values[primeMap]}];
  If[res=={}, {"unknown"}, res]];

compName[i_] := If[1<=i<=n, nodes[[i]], "?"];

Print["✅ 示例数据就绪：", nEvents, " 个事件，", n, " 个组件"];

(* ══════════════════════════════════════════════════
   Ex1：素数编码与解码（数学核心验证）
   ══════════════════════════════════════════════════ *)
Print["\n── Ex1：素数编码与解码 ──"];

(* 编码：timeout(2) × network_error(7) = 14 *)
composite = primeMap["timeout"] * primeMap["network_error"];
logVal    = Log[composite];
Print["timeout + network_error  →  composite = ", composite,
      "  log_value = ", N[logVal, 6]];

(* 解码：从 log_value 还原 *)
restored = decodeErrors[logVal];
Print["解码还原：", restored];
Assert[ContainsAll[restored, {"timeout", "network_error"}], "解码失败！"];
Print["✅ 编码/解码一致"];

(* 验证唯一性：10以内所有整数的解码 *)
Grid[
  Prepend[
    {#, N[Log[#],4], decodeErrors[Log[#]]} & /@
      Select[Range[1,20], IntegerQ[#] &],
    {"composite", "log_value", "解码结果"}],
  Frame -> All, Background -> {None, {LightGray, White}}]

(* ══════════════════════════════════════════════════
   Ex2：错误频率条形图
   ══════════════════════════════════════════════════ *)
Print["\n── Ex2：错误频率条形图 ──"];

allErrors = Flatten[decodeErrors[#[[4]]] & /@ events];
counts    = Sort[Normal[Counts[allErrors]], #1[[2]] > #2[[2]] &];

BarChart[counts[[All, 2]],
  ChartLabels -> Placed[counts[[All, 1]], Below],
  PlotLabel  -> "错误类型分布（" <> ToString[nEvents] <> " 个事件）",
  AxesLabel  -> {"错误类型", "出现次数"},
  ChartStyle -> "Pastel",
  GridLines  -> Automatic]

(* ══════════════════════════════════════════════════
   Ex3：组件对错误热力图
   ══════════════════════════════════════════════════ *)
Print["\n── Ex3：组件对错误热力图 ──"];

(* errorTensor[[caller, callee, t]] 在时间维度求和 *)
errMatrix = Total[Normal[errorTensor], {3}];

MatrixPlot[errMatrix,
  PlotLabel    -> "组件间累计错误量（log_value 之和）",
  FrameTicks   -> {Table[{i, nodes[[i]]}, {i,n}],
                   Table[{i, nodes[[i]]}, {i,n}]},
  FrameLabel   -> {"被调用者 (callee)", "调用者 (caller)"},
  ColorFunction -> "TemperatureMap",
  ColorFunctionScaling -> True,
  ImageSize    -> 300]

(* ══════════════════════════════════════════════════
   Ex4：时间序列折线图
   ══════════════════════════════════════════════════ *)
Print["\n── Ex4：时间序列（错误随时间变化）──"];

(* 每个事件的 log_value，0 表示 none *)
logValues = events[[All, 4]];

(* 以 0.5 秒为窗口，统计每窗口内错误事件数 *)
binSize = 0.5;
maxT    = Max[timestamps];
bins    = Table[
  Count[Pick[logValues, UnitStep[timestamps - t] - UnitStep[timestamps - t - binSize], 1], x_ /; x > 0],
  {t, 0, maxT - binSize, binSize}];
binTimes = Table[t, {t, 0, maxT - binSize, binSize}];

ListLinePlot[Transpose[{binTimes, bins}],
  PlotLabel  -> "每 0.5 秒窗口内的错误事件数",
  AxesLabel  -> {"时间（秒）", "错误事件数"},
  Filling    -> Axis,
  PlotStyle  -> Directive[Red, Thick],
  GridLines  -> Automatic]

(* ══════════════════════════════════════════════════
   Ex5：FFT 频谱分析（发现周期性规律）
   ══════════════════════════════════════════════════ *)
Print["\n── Ex5：FFT 频谱分析 ──"];

(* 将 log_value 重采样到均匀时间网格（线性插值） *)
nSamples  = 128;
tGrid     = Subdivide[0.0, Max[timestamps], nSamples - 1];
ifun      = Interpolation[Transpose[{timestamps, logValues}],
                           InterpolationOrder -> 1];
sampled   = ifun /@ tGrid;

spectrum = Abs[Fourier[sampled]];
halfSpec = spectrum[[1 ;; Floor[nSamples/2]]];
dt       = (Max[timestamps] - Min[timestamps]) / (nSamples - 1);
freqs    = Range[0, Floor[nSamples/2] - 1] / (nSamples * dt);

ListLinePlot[Transpose[{freqs, halfSpec}],
  PlotLabel -> "错误时间序列的 FFT 频谱",
  AxesLabel -> {"频率（Hz）", "幅度"},
  PlotStyle -> Directive[Purple, Thick],
  GridLines -> Automatic,
  PlotRange -> All]

(* ══════════════════════════════════════════════════
   Ex6：静态依赖网络图
   ══════════════════════════════════════════════════ *)
Print["\n── Ex6：静态依赖网络图 ──"];

depRules = Select[ArrayRules[staticDepA], #[[2]] =!= 0 &];

(* 关系类型素数 → 名称 *)
relNames = <|17->"db_query", 101->"runtime", 113->"cache"|>;

edges = (compName[#[[1,1]]] \[DirectedEdge] compName[#[[1,2]]]) & /@ depRules;
labels = Association[
  (compName[#[[1,1]]] \[DirectedEdge] compName[#[[1,2]]] ->
   Lookup[relNames, #[[2]], ToString[#[[2]]]]) & /@ depRules];

Graph[edges,
  EdgeLabels   -> labels,
  VertexStyle  -> Directive[LightSkyBlue, EdgeForm[Gray]],
  VertexSize   -> 0.3,
  EdgeStyle    -> Directive[Gray, Thick],
  GraphLayout  -> "LayeredDigraphEmbedding",
  PlotLabel    -> "静态依赖图"]

(* ══════════════════════════════════════════════════
   Ex7：调用者 / 被调用者错误排行
   ══════════════════════════════════════════════════ *)
Print["\n── Ex7：组件错误排行 ──"];

(* 各组件作为调用者产生的总错误（log_value 之和） *)
callerTotal = Table[Total[Normal[errorTensor][[i, All, All]], 2], {i, n}];
calleeTotal = Table[Total[Normal[errorTensor][[All, j, All]], 2], {j, n}];

callerRanked = SortBy[Transpose[{nodes, callerTotal}], -#[[2]] &];
calleeRanked = SortBy[Transpose[{nodes, calleeTotal}], -#[[2]] &];

Print["调用者（产生错误最多）："];
Print[callerRanked // TableForm];
Print["被调用者（接收错误最多）："];
Print[calleeRanked // TableForm];

BarChart[{callerTotal, calleeTotal},
  ChartLabels -> {Placed[nodes, Below], None},
  ChartLegends -> {"调用者", "被调用者"},
  PlotLabel   -> "各组件错误总量对比",
  ChartStyle  -> {"Orange", "SteelBlue"}]

(* ══════════════════════════════════════════════════
   Ex8：奇异值分解（SVD）— 提取主要错误模式
   ══════════════════════════════════════════════════ *)
Print["\n── Ex8：SVD 主要错误模式 ──"];

(* 将 errorTensor 展开为 (n×n) × T 矩阵 *)
errFlat = Flatten[Normal[errorTensor], 1]; (* (n*n) × T *)
(* 转置为 T × (n*n) 方便分析时间模式 *)
errMat  = Transpose[errFlat];              (* T × (n*n) *)

{u, s, v} = SingularValueDecomposition[errMat, Min[4, Dimensions[errMat]]];

(* 奇异值分布 — 解释了多少"错误方差" *)
singularVals = Diagonal[s];
ListPlot[singularVals,
  PlotLabel  -> "SVD 奇异值（前4个主成分）",
  AxesLabel  -> {"主成分序号", "奇异值"},
  PlotStyle  -> Directive[Red, PointSize[0.02]],
  Joined     -> True]

(* ══════════════════════════════════════════════════
   Ex9：异常检测（均值 ± 3σ 阈值法）
   ══════════════════════════════════════════════════ *)
Print["\n── Ex9：异常检测 ──"];

mu    = Mean[logValues];
sigma = StandardDeviation[logValues];
threshold = mu + 3 * sigma;

anomalyIdx = Flatten[Position[logValues, x_ /; x > threshold]];
Print["阈值（μ + 3σ）= ", N[threshold, 4]];
Print["检测到 ", Length[anomalyIdx], " 个异常事件"];

(* 标记异常点 *)
normalPts  = Transpose[{timestamps, logValues}];
anomalyPts = If[Length[anomalyIdx] > 0,
  Transpose[{timestamps[[anomalyIdx]], logValues[[anomalyIdx]]}],
  {}];

Show[
  ListLinePlot[normalPts,
    PlotStyle -> Directive[Gray, Thin],
    PlotLabel -> "错误时间序列 + 异常点标记"],
  If[Length[anomalyPts] > 0,
     ListPlot[anomalyPts, PlotStyle -> Directive[Red, PointSize[0.015]]],
     Graphics[]],
  Graphics[{Dashed, Orange,
            Line[{{0, threshold}, {Max[timestamps], threshold}}]}],
  AxesLabel -> {"时间（秒）", "log_value"}]

(* ══════════════════════════════════════════════════
   Ex10：马尔可夫链 — 错误传播概率
   ══════════════════════════════════════════════════ *)
Print["\n── Ex10：马尔可夫链（错误传播）──"];

(* 构建组件间错误转移计数矩阵 *)
(* 如果事件 i 的 callee = 事件 i+1 的 caller，认为存在传播 *)
transCount = ConstantArray[0, {n, n}];
Do[
  If[events[[i, 4]] > 0 && events[[i+1, 4]] > 0,  (* 两者都有错误 *)
     transCount[[ events[[i, 3]], events[[i+1, 2]] ]] += 1],
  {i, nEvents - 1}];

(* 归一化为概率矩阵（每行除以行和，行和为0则保持0） *)
transProb = Table[
  Module[{rowSum = Total[transCount[[i]]]},
    If[rowSum > 0, transCount[[i]] / rowSum, transCount[[i]]]],
  {i, n}];

Print["错误传播转移概率矩阵："];
Grid[
  Prepend[
    MapThread[Prepend, {N[transProb, 3], nodes}],
    Prepend[nodes, ""]],
  Frame -> All,
  Background -> {None, {LightGray, White}}]

MatrixPlot[transProb,
  PlotLabel  -> "错误传播转移概率（马尔可夫链）",
  FrameTicks -> {Table[{i, nodes[[i]]}, {i,n}],
                 Table[{i, nodes[[i]]}, {i,n}]},
  ColorFunction -> "BlueGreenYellow",
  ImageSize  -> 280]

Print["\n✅ 全部 10 个例子执行完毕。"];
