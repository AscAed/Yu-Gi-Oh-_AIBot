# Rabbit终场采集两次验真实施计划

**Goal:** 验证修复后的worker完成Rabbit精确终场14项查询及独立重放。

**Architecture:** 复用采集与独立校验；新terminal-smoke-v1单例scope固定2次，旧scope保持原语义。Python冻结来源、构建、双资产、CDB类型表和请求，Rust统一收费并在重放前执行门禁。

**Tech Stack:** Rust workspace、Python标准库及现有测试工具；无新增外部服务。

**Spec:** 用户批准的Rabbit两次方案；当前状态仅维护TASKS，证据追加TESTING。

## 固定边界

- 保留未提交修改和历史18次、未知0；旧窗口剩余5次不续用。新目录p1-terminal-smoke-2026-10-20独占建立，窗口在首次候选扫描前保存，2小时不重置。
- 新请求仅替换worker路径，保留原冻结Rabbit完整牌组、五张起手、seed、采集策略、20项决策和prompt ID；不调整线路重试。
- 单worker30秒，执行及重放各一次。查询/探针不额外安排；内部FFI计数与worker请求分别报告。
- 正常边界为首个下一回合NEW_TURN的核心处理返回点；phase未知。不实现求解器、赛事或洗手牌原生扩展，不切换dist、原worker或active，不自动提交/推送Git。

## 独立交付任务

- [ ] 只读提取历史43字节查询，核验哈希及冻结核心IS_PUBLIC行为；分别验证生产和独立解析。覆盖缺省/0/1、重复、非法布尔、长度、截断及缺失END；完整合成查询集不作为原生证据。
- [ ] 为新2次预算、单例runner门禁及报告合同先观察失败测试，再实现和复验。batch_kind缺省仍原6次；新值terminal-smoke-v1只接受terminal-rabbit和预期值1。
- [ ] Python terminal-smoke提供cases、baseline-dir、runner、worker、build-record、identity、window-start、output及prepare-only；验证历史acceptance/checkpoint/账本/保护哈希，旧失败收据使用保存原runner零调用验证。
- [ ] manifest/pair/summary独立v1合同在原生前覆盖成功、单次失败、未完成及消费未知；历史18、本批实际0–2，不自签证明资格。
- [ ] 完成总检及独立审阅，保存原生构建关联、源码和产物副本；先保存窗口，再重复采集双资产身份并冻结具体请求。
- [ ] 执行后须无错误/待提示/未决消费，决策完整，14查询和边界独立绑定、计数效用1、响应审计及资产身份通过，才允许重放；重放后完整比较事件/批次/原始查询/快照/决策。
- [ ] 任一异常即停，已收费结果保留；不退款、不重发、不换窗口。完整结果零调用恢复。

## 复验与收尾

- [ ] Rust格式、Clippy全目标、workspace默认测试集（Windows串行）、example及Python全套；跳过项逐项列明。
- [ ] stub证明查询/响应审计/资产失败时重放次数0；预算第三次、重复、错请求/目的、到期及未知消费均在收费前拒绝。
- [ ] 分别保存原生时点与文档收尾后的源码/构建/双资产身份；源码归档、文件清单、验收和下一断点核对哈希。
- [ ] 累计按18+实际消费报告。成功仅授予该Rabbit线路的终场绑定及独立重放证据，proof_ready、complete_action_coverage、global_optimality仍false。
- [ ] 无论成败，本批收尾暂停；赛事和洗手牌后结束另定预算。
