(* ═══════════════════════════════════════════════════════════
   wl_bridge/errors.wl
   输出：TSV，两列 error_type / count
   用法：wolfram -script errors.wl [json文件路径]
   ═══════════════════════════════════════════════════════════ *)

file = If[Length[$ScriptCommandLine] > 0,
  $ScriptCommandLine[[1]],
  (* 默认：找当前目录最新的 error_events_*.json *)
  First[Sort[FileNames["error_events_*.json"], Greater], ""]
];

If[file == "" || !FileExistsQ[file],
  Print["ERROR\tcannot find error_events_*.json"];
  Exit[1]
];

json     = Import[file, "RawJSON"];
pm       = json["prime_map"];
events   = json["events"];

decodeLog[lv_] := Module[{c = Round[Exp[lv]], res = {}},
  If[c <= 1, Return[{"none"}]];
  KeyValueMap[
    Function[{name, p},
      If[p > 1 && Mod[c, p] == 0,
        AppendTo[res, name];
        While[Mod[c, p] == 0, c = Quotient[c, p]]]],
    pm];
  If[res == {}, {"unknown"}, res]];

counts = <||>;
Do[
  Do[counts[e] = Lookup[counts, e, 0] + 1,
     {e, decodeLog[ev[[4]]]}],
  {ev, events}];

(* 过滤 none，按频次降序 *)
nonNone = Select[Normal[counts], First[#] != "none" &];
sorted  = SortBy[nonNone, -Last[#] &];

Print["error_type\tcount"];
Do[Print[kv[[1]], "\t", kv[[2]]], {kv, sorted}];
