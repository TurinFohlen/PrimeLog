(* ═══════════════════════════════════════════════════════════
   wl_bridge/timeseries.wl
   输出：TSV，三列 t / error_count / none_count（滑动窗口）
   用法：wolfram -script timeseries.wl [json文件路径] [窗口大小秒]
   ═══════════════════════════════════════════════════════════ *)

args = $ScriptCommandLine;
file = If[Length[args] > 0, args[[1]],
  First[Sort[FileNames["error_events_*.json"], Greater], ""]];
binSize = If[Length[args] > 1, ToExpression[args[[2]]], 1.0];

If[file == "" || !FileExistsQ[file],
  Print["ERROR\tcannot find file"];
  Exit[1]
];

json       = Import[file, "RawJSON"];
events     = json["events"];
timestamps = json["timestamps"];

logValues = events[[All, 4]];
maxT      = Max[timestamps];
steps     = Range[0, maxT - binSize, binSize];

Print["t\terror_count\tnone_count"];
Do[
  inBin    = Pick[logValues,
               (UnitStep[timestamps - t] - UnitStep[timestamps - t - binSize]),
               1];
  errCount = Count[inBin, x_ /; x > 0];
  noneCount= Count[inBin, 0.0];
  Print[NumberForm[t, {6,3}], "\t", errCount, "\t", noneCount],
  {t, steps}];
