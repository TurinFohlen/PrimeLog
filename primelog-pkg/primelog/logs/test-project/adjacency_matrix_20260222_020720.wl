(* ============================================================
   静态依赖矩阵 A - 由 error_log.py 自动生成
   生成时间: 20260222_020720    组件数量: 3
   使用方式: Get["adjacency_matrix.wl"]
   ============================================================ *)

nodes = {"primelog.core.orchestrator", "test-project.compA", "test-project.compB"};  (* 组件名列表，索引从1开始 *)
n = 3;             (* 组件总数 *)

staticDepA = SparseArray[{{2,3}->1, {3,2}->1}, {3,3}];

(* 查看矩阵: MatrixForm[Normal[staticDepA]] *)
(* 找出所有依赖对: Position[Normal[staticDepA], 1] *)