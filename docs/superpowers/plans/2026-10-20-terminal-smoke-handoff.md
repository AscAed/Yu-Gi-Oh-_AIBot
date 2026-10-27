# Rabbit终场两次验真断点

先读docs/INDEX.md、TASKS.md、TESTING.md顶部，再核对本机`data/runtime/p1-terminal-smoke-2026-10-20/acceptance.json`及delivery-checkpoint.json。保留所有未提交修改、历史数据和部署，不从HEAD恢复或覆盖原目录。

本批独立terminal-smoke-v1 scope上限2次，已完成Rabbit执行和独立重放。两次均engine_verified，目标查询14+14，边界绑定有效、计数和正常效用均1；事件、原始处理批、查询、快照、决策及资产一致。实际消费2次、未知0；旧三账本9+8+1不变，累计20次。旧6次窗口剩余5次继续冻结，新2次窗口已用满，不能继续、退款或换ID续费。

正常边界仍为首个下一回合NEW_TURN所在核心处理返回点，包含部分新回合初始化。实际边界事件63/批60由原始消息重算，未硬编码；phase保持未知。目标FFI查询28次，legacy查询总数null，不将内部查询误计为额外worker请求。原生结果保存点753秒，阶段收尾含零调用恢复及离线复核880秒。

原生时点源码身份为1ed1abc02994bf06f755a3de450b05b4f8597c6395dda6f84d9e70fa48f37a39，源码归档/构建/双资产身份和五份产物副本分别保存。最终文档后的身份以acceptance.json及delivery-source.json为准，避免文档自引用。research/native保存不可覆盖请求、pair、manifest、summary及账本收据；新账本SHA为624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0。

恢复验证使用保存的native-artifacts/terminal-regression.exe、原terminal-rabbit-input.json及其SHA并带`--verify-recorded`，只读且零调用。Python重开在原生冻结源码时已经验证；文档收尾后源码身份不同，不运行原完整编排来获取新资格。零调用恢复记录、原生及最终v2离线报告各自保留，不重写上批失败。

下一步先审阅本批证据和输入合同，再单独制定赛事完整线路、洗手牌后结束的预算。它们尚未获得本采集策略下的终场绑定资格；不自动启动。剩余提示、信息/概率、动作顺序、循环、自然结束和树规模仍阻断完整性证明，research-problem候选不因单条成功线路变为proof_ready。

本批只授予冻结Rabbit线路的终场绑定及独立重放证据。proof_ready、complete_action_coverage、global_optimality均false；不提升正式v6或全卡资格，不实现求解器，不自动提交/推送Git。
