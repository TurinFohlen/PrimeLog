(* ═══════════════════════════════════════════════════════════
   wl_bridge/heatmap.wl
   输出：先输出节点名（TAB分隔），再输出矩阵行（TAB分隔数值）
   用法：wolfram -script heatmap.wl [events_json] [adj_json]
   ═══════════════════════════════════════════════════════════ *)

args     = $ScriptCommandLine;
evFile   = If[Length[args] > 0, args[[1]],
  First[Sort[FileNames["error_events_*.json"],  Greater], ""]];
adjFile  = If[Length[args] > 1, args[[2]],
  First[Sort[FileNames["adjacency_matrix_*.json"], Greater], ""]];

If[!FileExistsQ[evFile] || !FileExistsQ[adjFile],
  Print["ERROR\tmissing files"];
  Exit[1]
];

evJson  = Import[evFile,  "RawJSON"];
adjJson = Import[adjFile, "RawJSON"];

nodes  = adjJson["nodes"];
n      = Length[nodes];
events = evJson["events"];

(* 短名（取最后一段）便于显示 *)
shortName[s_] := Last[StringSplit[s, "."]];

(* 构建 caller×callee 错误累计矩阵（只算有错误的事件 log_value > 0）*)
mat = ConstantArray[0.0, {n, n}];
Do[
  If[ev[[4]] > 0,  (* log_value > 0 表示有错误 *)
    ci = ev[[2]] + 1;  (* JSON 0-indexed -> WL 1-indexed *)
    ei = ev[[3]] + 1;
    If[1 <= ci <= n && 1 <= ei <= n,
      mat[[ci, ei]] += ev[[4]]]],
  {ev, events}];

(* 输出节点名行 *)
Print["NODES\t", StringRiffle[shortName /@ nodes, "\t"]];

(* 输出矩阵，每行 caller 名 + 各列数值 *)
Do[
  Print[shortName[nodes[[i]]], "\t",
        StringRiffle[ToString[NumberForm[#, {4,2}]] & /@ mat[[i]], "\t"]],
  {i, n}];
