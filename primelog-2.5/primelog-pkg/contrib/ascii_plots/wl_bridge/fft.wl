(* ═══════════════════════════════════════════════════════════
   wl_bridge/fft.wl
   输出：TSV，两列 freq_bin / amplitude（归一化）
   用法：wolfram -script fft.wl [json文件路径] [bin秒数]
   ═══════════════════════════════════════════════════════════ *)

args    = $ScriptCommandLine;
file    = If[Length[args] > 0, args[[1]],
  First[Sort[FileNames["error_events_*.json"], Greater], ""]];
binSize = If[Length[args] > 1, ToExpression[args[[2]]], 0.5];

If[!FileExistsQ[file], Print["ERROR\tmissing file"]; Exit[1]];

json       = Import[file, "RawJSON"];
events     = json["events"];
timestamps = json["timestamps"];

logValues = events[[All, 4]];
maxT      = Max[timestamps];

(* 时间序列：每个 bin 的错误数 *)
series = Table[
  Count[Pick[logValues,
    UnitStep[timestamps - t] - UnitStep[timestamps - t - binSize], 1],
    x_ /; x > 0],
  {t, 0, maxT - binSize, binSize}];

If[Length[series] < 4, Print["ERROR\ttoo few points"]; Exit[1]];

(* FFT，取前半段（奈奎斯特），归一化 *)
n        = Length[series];
spectrum = Abs[Fourier[N[series]]];
halfN    = Floor[n/2];
amps     = spectrum[[2 ;; halfN + 1]];  (* 跳过直流分量 *)
maxAmp   = Max[amps];
normAmps = If[maxAmp > 0, amps / maxAmp, amps];

sampleRate = 1.0 / binSize;
freqs = Table[k * sampleRate / n, {k, 1, halfN}];

Print["freq_hz\tamplitude"];
Do[Print[NumberForm[freqs[[i]], {6,4}], "\t",
         NumberForm[normAmps[[i]], {6,4}]],
   {i, Length[freqs]}];
