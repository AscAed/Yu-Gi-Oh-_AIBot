# H3.2-1 后项目评估与双轨实施路线

日期：2026-11-01。基线为 main / `6b523f2` 加已有未提交源码及文档；HEAD 不是完整工作区身份。当前状态以 [TASKS](../../../TASKS.md) 为准，目标以 [PRODUCT_VISION](../../PRODUCT_VISION.md) 为准，历史验证以 [TESTING](../../TESTING.md) 为准。

## 定位与差距

项目是具备牌组草稿工作台的有限场景研究原型。P0 已有身份及清点工具，正式 OCG 发行分母未闭合；P1 有局部协议、观察和原生证据，完整动作、条件概率、信息策略、循环和独立值界尚未闭合。P2/P3 有 39 卡字段盘点、草稿 CLI 和开发浏览器工作台，正式中文数据、真实分析及普通发布包仍缺。P4/R1 有合成恢复及有限场景重放基础，真实进程恢复和独立原生重放未认证，R2–R5 开放。P5–P8 的通用知识、构筑反馈、全卡覆盖及可核查最优性证明未完成。

H2.2 所列合成门禁关闭；H3.1 完成[恢复设计](2026-11-01-w1h31-cross-chain-recovery-design.md)，H3.2-1 已完成[认证恢复合成验收](2026-11-01-w1h321-recovery-handoff.md)，H3.2-2 完整响应丢失和目标窗口强杀矩阵仍开放，普通启动仍为 `analysis_not_configured`。基础工具可按工程小批推进；全卡和最优性存在未证明可行的研究关口，无法可信计算总完成比例或最终工期。

## 需求追踪

| 愿景 ID | 当前缺口及后续阶段 | 证据与验收入口 |
|---|---|---|
| UX-01 | 工作台真实分析及发布，W1-C/W2 | TASKS、WORKBENCH、TESTING |
| LANG-01 | 正式中文搜索，L1/P2 | LANGUAGE_REVIEW、PRODUCT_VISION |
| LANG-02 | 中文意图与双语，P3/P8 | PRODUCT_VISION、ROADMAP |
| DATA-01 | 版本更新及回滚，P2/P8 | PRODUCT_VISION、ROADMAP |
| DATA-02 | 正式发行分母和脚本依赖，P0/P8 | PRODUCT_VISION、TASKS |
| DECK-01 | 草稿与往返已有基础，发布验收待完成，W2 | WORKBENCH、TESTING |
| BUILD-01 | 约束下补全优化，P6 | PRODUCT_VISION、ROADMAP |
| BUILD-02 | 多主题自主构筑，P5/P6 | PRODUCT_VISION、ROADMAP |
| KNOW-01 | 可证互动检索，P5/P6 | PRODUCT_VISION、ROADMAP |
| COMBO-01 | 主题玩法与互动识别，P5/P6 | PRODUCT_VISION、ROADMAP |
| COMBO-02 | 合法起手策略及完整性证明，P1/P7/P8 | OPTIMALITY_RESEARCH、TASKS |
| COMBO-03 | 干扰响应及损失比较，P4/P7 | ROADMAP、TASKS |
| LOOP-01 | 同口径配对与留出评估，P6 | PRODUCT_VISION、ROADMAP |
| KNOW-02 | 引擎来源关系网与安全剪枝，P1/P5/P7 | OPTIMALITY_RESEARCH、EVIDENCE_CONTRACTS |
| ENG-01 | 替代引擎兼容认证，P8 | PRODUCT_VISION、ROADMAP |
| TRUST-01 | 来源、重放与独立证明，全部阶段 | EVIDENCE_CONTRACTS、TESTING |

上述入口均为 docs 下同名 Markdown；状态及具体验证条件以对应事实源为准。

## 双轨小步安排

| 批次 | 可独立验收的成果与停止条件 |
|---|---|
| D12 | 需求、H3.1、部署身份与开放门禁一致；历史修改完整保留 |
| H3.2-1 | 已完成认证、关联修复、重启分类及重复重开的限定合成验收；范围见交接 |
| H3.2-2a | 固定 HTTP 响应丢失情景，验证持久状态、只读查询、幂等恢复及不自动重发 |
| H3.2-2b | 用明确握手验证跨链目标窗口强杀及重复重开；逐 syscall、断电和介质故障另列未知 |
| W1-C | 合成门禁后设计固定 Rabbit 输入、资产、预算、调用及停止条件；真实执行另行安排 |
| L1 | 逐批核验 39 卡名称、正文、别名、语言类别和使用、再分发依据，缺证保持未知；可与工作台并行 |
| R1b-3 | 设计独立 scope、预算、消费、暂停重开及独立重放；真实执行另行授权 |
| P4-R5 / W2 | 先确定可比账本及口径，再设计双资产与干净环境启动、路径、草稿、导入导出和升级验收；分别绑定源码、产物和资产 |
| P1 | 每批选择动作完整性、观察投影、条件概率、自然结束或循环之一，交付可复现结论 |
| M1 | 按人时、耗时、内存、调用和证据体积复盘；P4 按 R2→R3→R4→R5 资格依赖推进 |

逐卡人工模型适合定向认证但全卡维护成本高；完整引擎搜索保留执行权威，但完整动作及证明规模未解。推荐研究语义辅助排序、引擎执行、独立证明：只有可独立核查的安全依据才能用于证明性剪枝。

## 部署与证据边界

旧普通包 CLI 和 worker 的 SHA-256 与包内清单匹配，只证明所查文件身份；该 2026-10-19 包不证明当前源码已部署。历史 `a21d587` 隔离候选普通及赛事诊断、各 3/3 replay 按 [TESTING](../../TESTING.md) 的资产及范围引用；两次 smoke 受预算截断，缺少可比账本，P4-R5 开放。H2.2-B 的 16 轮竞争均为 claim 获胜，取消先完成仅有顺序用例；早期 TCP 重置根因未知。Tenki 原 pin、Curry 来源链缺口及历史账本保留，哈希清单不是备份。
