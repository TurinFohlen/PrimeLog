(* ============================================================
   错误事件列表（素数编码）- 由 error_log.py 自动生成
   生成时间: 20260222_020720    事件数量: 2
   使用方式: Get["error_events.wl"]
   注意: 需同时加载 adjacency_matrix.wl 以获取 n 和 nodes
   ============================================================ *)

primeMap = <|"none"->1, "timeout"->2, "permission_denied"->3, "file_not_found"->5, "network_error"->7, "disk_full"->11, "auth_failed"->13, "unknown"->17, "execution_error"->19|>;

timestamps = {"2026-02-22T02:07:20.123932", "2026-02-22T02:07:20.124102"};  (* 与 events 对应的时间戳列表 *)

(* 事件格式: {t, caller_index, callee_index, composite_value} *)
events = {
  {1,2,3,1},
  {2,2,3,17}
};
totalT = 2;

(* 三维稀疏对数错误张量 errorTensor[[caller, callee, t]] *)
(* 需先加载 adjacency_matrix.wl 以获得 n *)
errorTensor = SparseArray[{
  {2,3,2}->2.83321334
}, {3,3,2}];

(* ─── 后续分析示例 ─── *)
(* 可以将 timestamps 转换为 AbsoluteTime 用于时域分析 *)
(* absoluteTimes = AbsoluteTime /@ timestamps; *)
(* receivedError = Table[Total[Normal[errorTensor][[All,j,All]],2],{j,n}]; *)
(* producedError = Table[Total[Normal[errorTensor][[i,All,All]],2],{i,n}]; *)