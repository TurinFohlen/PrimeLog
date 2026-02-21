(* ============================================================
   静态依赖矩阵（带权）- 由 error_log.py 自动生成
   生成时间: 20260222_021400    组件数量: 3
   使用方式: Get["adjacency_matrix.wl"]
   ============================================================ *)

nodes = {"primelog.core.orchestrator", "test-project.compA", "test-project.compB"};  (* 组件名列表，索引从1开始 *)
n = 3;             (* 组件总数 *)

relationPrimeMap = <|"internal.sync"->2, "internal.async"->3, "internal.event"->5, "internal.config"->7, "internal.registry"->11, "runtime"->13, "rpc"->17, "db_query"->19, "file_io"->23, "http_request"->29, "pipeline"->31, "init"->37, "destroy"->41, "health_check"->43, "metrics"->47, "config_read"->53, "config_write"->59, "cache"->61, "lock"->67, "transaction"->71, "validation"->73, "notification"->79|>;

staticDepA = SparseArray[{{2,3}->2, {3,2}->13}, {3,3}];

(* 查看矩阵: MatrixForm[Normal[staticDepA]] *)
(* 找出所有依赖对及其类型: Select[ArrayRules[staticDepA], #[[2]]!=0 &] *)