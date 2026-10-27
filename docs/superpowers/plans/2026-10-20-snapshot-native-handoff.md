# 快照评价与小批回归断点

实时状态仍只见TASKS，实跑见TESTING。本文件用于从本批证据继续，不把未运行组视为成功。

## 已保留的边界

- HEAD为8a6b2f6762131aebea6d8c0f5f61363d573f1b36，源码修改未提交。保留整个工作区，不从HEAD恢复覆盖。
- 忽略证据根目录为`data/runtime/p1-state-native-2026-10-20/`。原生时点源码身份为`a94c197d198630d5a483a4b3f74f7a34dfeb42cf877d35196b2cd38a2ada55aa`，见build-native.json、workspace-native.json、native-source.zip及native-artifacts。最终文档后的构建和源码归档另存build-final.json、workspace-final.json、delivery-source.zip与清单。
- 原9次账本SHA为`b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a`。本批独立账本实际8次，unknown/reserved均0，累计17次；原文件、blob和原worker/config均不覆盖。
- 新窗口起点1792431055，在候选双资产扫描前保存。manifest和起点sidecar绑定输出目录与上下文。重开不能重置起点、退款或另换账本；原计划未执行2次及储备6次都不自动使用。

## 原生结果与实际故障

前三组Rabbit完整线路、赛事完整线路、Rabbit空决策前缀均通过执行/重放和资产一致性。空前缀实际idle prompt ID为7，合法命令8存在。第四组由该公开菜单派生，实际请求被接受，独立重放一致；随后prompt ID为9，洗手牌选项关闭，手牌多重集不变。

初次观察器要求整份历史恰好一条己方洗手牌消息，但完整历史包含初始化消息及命令8新增消息，因而误报group_observation_failed。编排立即停止，第五组未运行。原summary和失败退出记录保留；旧源码重开完整编排仅验证既有四组，账本字节未变、新增调用0。

停止后只修复离线检查：先验证子历史保留父历史为精确前缀，再检查新增后缀的一条己方洗手牌消息。复核另存，不重写原生summary或账本，不在修改后继续原生组。原生时点源码与最终源码分别关联；离线复核不是新的原生重放。

## 续接入口

1. 先读docs/INDEX.md、TASKS.md、docs/TESTING.md及acceptance.json和delivery-checkpoint.json；核对源码归档、文件清单和原账本哈希。源码身份如已变化，先解释差异，不覆盖现有工作区。
2. 只读核验既有原生报告可用保留的native-artifacts/native-regression.exe，对原`*-input.json`传入`--input-sha <该文件SHA256> --verify-recorded`。此模式从同一账本验证不可覆盖收据、实际结果、响应集合和重放，不启动worker；现有输入/账本缺失时拒绝。
3. 不直接重跑已修复的编排器以补第五组。先审阅初次故障、离线复核及未触达项，再为剩余命令7前缀或新问题单独冻结计划和原生预算。
4. 精确终场捕获需要独立协议与查询绑定设计；当前固定checkpoint标签及下一回合消息不提供该证明。后续另设计P1.2状态目标合同，不能偷偷改变research-case v1固定normal语义。
5. 命令6及opcode13/14/24若未触达继续留缺口；随机/隐藏信息/顺序/循环和完整树规模仍未解决，不实现完整树搜索或授予全局最优。全卡、正式v6、普通dist与active快照不因本批升级。

最终验收清单分别记录工具验证、快照值、终场可信度、原生线路与重放、实际消费、耗时和证据体积。proof_ready、complete_action_coverage、global_optimality始终为false。
