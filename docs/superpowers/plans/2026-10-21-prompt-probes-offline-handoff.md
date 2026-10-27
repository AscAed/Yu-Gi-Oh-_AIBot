# 剩余提示静态准备：续接断点

本批按[实施计划](2026-10-21-prompt-probes-offline.md)完成后暂停。当前状态以TASKS及TESTING为准，完整源码、工具身份、来源/候选哈希、实跑日志和验收在忽略目录`data/runtime/p1-prompt-probes-offline-2026-10-21`。恢复先核对acceptance.json、delivery-checkpoint.json、final-source.json及五份旧账本，不从HEAD覆盖未提交工作。

## 交付及限制

入口为prepare-prompt-probes，正式输出在`research-final/report.json`及`prepared-cases.json`。三个候选仅替换原Rabbit主卡及起手中的85138716，保留40/3/0、seed1，并同步worker复制己方牌组的对手资源声明。Tenki、Mooyan Curry、Ground Collapse分别针对13、14、24；唯一激活项选择不猜prompt或菜单索引。

发行依据未知，静态API路径不认证原生可达或响应接受。24实际掩码待未来原始提示；RECOVER92/FIELD_DISABLED56后继支持尚缺。命令6没有可执行候选：当前规则未启用首回合战斗，worker在下一回合开始停止，静态直接符号扫描不是动态例外不存在的证明。

## 下一批启动条件

先审阅候选、来源和消息依赖，再单独制定探索、响应验证和独立重放的原生预算。实际worker、公开菜单、prompt、具体请求内容哈希、scope及时间窗须在新收费前冻结。所有发现提示、查询、失败和重试均计费，不能直接把准备合同提交给worker。没有唯一激活项即停止，不调整线路重试。

本批无新原生/FFI查询，无新窗口或收费账本。五份旧账本累计24、未知0，所有旧窗口封存；不切换普通dist、active或worker，不自动提交推送。execution_ready、native_reachability_verified、response_acceptance_verified、proof_ready、complete_action_coverage、global_optimality及native_probability_verified均false。

## 后续状态勘误（2026-10-27）

本文件上述消息支持缺口反映2026-10-21当时状态。后续生产decoder已增加opcode92 `RECOVER`及opcode56 `FIELD_DISABLED`的严格帧解析；这只验证通用协议帧，不证明两类消息在Ground Collapse线路中出现、顺序正确或响应被引擎接受。Tenki opcode13与Mooyan Curry opcode14后来分别获得冻结案例的局部原生分支及独立重放证据，但不代表Rabbit完整动作树覆盖。Ground Collapse opcode24仍未原生触达，实际掩码、prompt ID、可达性、响应接受及后继消息序列均未知。当前离线选区准备见[2026-10-27 Ground Collapse交接](2026-10-27-ground-collapse-preparation-handoff.md)。
